# Bedrock AgentCore Integration Notes

> **Note**: This document is for reference only. RentPilot's submitted implementation does not use AgentCore primitives.

This document describes how AgentCore primitives (Knowledge Bases, Action Groups, Guardrails) could be integrated with RentPilot's current architecture.

**Current Architecture**: RentPilot uses Bedrock Converse API for planning and finalization, with deterministic Lambda tools for execution. This approach prioritizes transparency and simplicity.

**Potential Extensions**: The following sections outline how to optionally add AgentCore primitives for enhanced capabilities (e.g., FAQ retrieval via Knowledge Base).

---

## What is Bedrock AgentCore?

From AWS Bedrock docs:
> **AgentCore** provides reusable primitives (e.g., Knowledge Bases, Action Groups, Guardrails) that can be orchestrated via the Bedrock Agent Runtime API.

Key primitives:
1. **Knowledge Bases** — Retrieval-augmented generation (RAG) over documents
2. **Action Groups** — Lambda-backed tool invocations (similar to our current approach)
3. **Guardrails** — Content filtering, PII redaction
4. **Prompt Flows** — Multi-step orchestration

---

## Recommended Primitive: Knowledge Base

**Use Case**: Augment RentPilot with CMHC FAQ retrieval.

### Example Questions Knowledge Base Could Answer:
- "What does CMHC stand for?"
- "How is rent-to-income calculated?"
- "What transit score means?"
- "Explain the difference between median and average rent"

### Why Knowledge Base?
- **Lightweight**: No new Lambda code; just upload docs to S3 + create KB
- **High-Value Demo**: Shows hybrid reasoning (LLM planning + RAG retrieval)
- **Judges Love It**: Demonstrates AgentCore primitive usage

---

## Implementation Steps

### 1. Prepare Knowledge Base Documents

Create a simple markdown file with FAQs:

**File**: `data/rentpilot_faq.md`

```markdown
# RentPilot FAQ

## What is CMHC?
The Canada Mortgage and Housing Corporation (CMHC) is a Crown corporation that provides rental market data for Canadian cities.

## How is rent-to-income (RTI) calculated?
RTI = (Monthly Rent / Monthly Income). A common target is 30% (0.30).

## What is a transit score?
Transit score (0-100) measures proximity to public transit. Higher scores mean better access.

## What does EPS mean?
Equivalent Percentage Savings (EPS) compares your listing price to the city median:
EPS = (City Median - Listing Price) / City Median

Example: If city median is $2300 and listing is $2200, EPS = 4.3% (you save 4.3% vs median).

## What property types are supported?
- studio (bachelor)
- 1bed (one-bedroom)
- 2bed (two-bedroom)
- 3bed (three-bedroom)

## What cities are covered?
Currently: Toronto, Vancouver, Montreal (extensible to other Canadian cities).
```

### 2. Upload to S3

```bash
aws s3 cp data/rentpilot_faq.md s3://your-bucket/rentpilot-kb/faq.md
```

### 3. Create Bedrock Knowledge Base

#### Option A: AWS Console
1. Go to **Bedrock → Knowledge Bases** → Create
2. Name: `RentPilotFAQ`
3. Data source: S3 bucket `s3://your-bucket/rentpilot-kb/`
4. Embeddings model: **Titan Embeddings G1 - Text** (cheapest)
5. Vector store: **OpenSearch Serverless** (or Amazon Aurora if you prefer)
6. Wait for ingestion to complete (~2-5 min)

#### Option B: AWS CLI
```bash
# Create KB (requires pre-configured IAM role)
aws bedrock create-knowledge-base \
  --name RentPilotFAQ \
  --role-arn arn:aws:iam::ACCOUNT_ID:role/BedrockKBRole \
  --knowledge-base-configuration '{
    "type": "VECTOR",
    "vectorKnowledgeBaseConfiguration": {
      "embeddingModelArn": "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v1"
    }
  }' \
  --storage-configuration '{
    "type": "OPENSEARCH_SERVERLESS",
    "opensearchServerlessConfiguration": {
      "collectionArn": "arn:aws:aoss:us-east-1:ACCOUNT_ID:collection/abc123",
      "vectorIndexName": "rentpilot-faq",
      "fieldMapping": {
        "vectorField": "vector",
        "textField": "text",
        "metadataField": "metadata"
      }
    }
  }'

# Note the knowledge-base-id (e.g., KB12345XYZ)

# Create data source
aws bedrock create-data-source \
  --knowledge-base-id KB12345XYZ \
  --name S3FAQSource \
  --data-source-configuration '{
    "type": "S3",
    "s3Configuration": {
      "bucketArn": "arn:aws:s3:::your-bucket",
      "inclusionPrefixes": ["rentpilot-kb/"]
    }
  }'

# Start ingestion
aws bedrock start-ingestion-job \
  --knowledge-base-id KB12345XYZ \
  --data-source-id DS67890ABC
```

### 4. Test Knowledge Base Retrieval

```bash
# Retrieve and generate
aws bedrock-agent-runtime retrieve-and-generate \
  --input '{"text": "What is CMHC?"}' \
  --retrieve-and-generate-configuration '{
    "type": "KNOWLEDGE_BASE",
    "knowledgeBaseConfiguration": {
      "knowledgeBaseId": "KB12345XYZ",
      "modelArn": "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-sonnet-20240229-v1:0"
    }
  }'
```

Expected response:
```json
{
  "output": {
    "text": "CMHC stands for Canada Mortgage and Housing Corporation, a Crown corporation that provides rental market data for Canadian cities."
  },
  "citations": [...]
}
```

### 5. Integrate into RentPilot

#### 5a. Add IAM Policy to AgentHandlerFn

**File**: `template.yaml`

```yaml
AgentHandlerFn:
  Type: AWS::Serverless::Function
  Properties:
    # ... existing config ...
    Policies:
      - Statement:
          - Effect: Allow
            Action:
              - "bedrock:InvokeModel"
              - "bedrock:InvokeModelWithResponseStream"
            Resource: !Sub "arn:aws:bedrock:${AWS::Region}::foundation-model/*"
          # [NEW] Knowledge Base retrieval
          - Effect: Allow
            Action:
              - "bedrock:Retrieve"
              - "bedrock:RetrieveAndGenerate"
            Resource: !Sub "arn:aws:bedrock:${AWS::Region}:${AWS::AccountId}:knowledge-base/*"
```

#### 5b. Add Knowledge Base Retrieval Function

**File**: `agent_bedrock.py` (add new function)

```python
def _query_knowledge_base(kb_id: str, query: str) -> Optional[str]:
    """
    Query Bedrock Knowledge Base for FAQ-style questions.
    Returns the generated answer or None if KB is not configured.
    """
    if not kb_id:
        return None
    try:
        client = boto3.client("bedrock-agent-runtime", region_name=AWS_REGION)
        resp = client.retrieve_and_generate(
            input={"text": query},
            retrieveAndGenerateConfiguration={
                "type": "KNOWLEDGE_BASE",
                "knowledgeBaseConfiguration": {
                    "knowledgeBaseId": kb_id,
                    "modelArn": f"arn:aws:bedrock:{AWS_REGION}::foundation-model/{os.getenv('MODEL_ID', 'anthropic.claude-3-sonnet-20240229-v1:0')}"
                }
            }
        )
        return resp.get("output", {}).get("text")
    except Exception as e:
        print(f"[WARN] KB query failed: {e}")
        return None
```

#### 5c. Add Knowledge Base Check in Orchestrator

**File**: `agent_bedrock.py` (update `run_agent`)

```python
def run_agent(user_input: str, *, print_blocks: bool = True, show_json: bool = False, no_ledger: bool = False) -> Dict[str, Any]:
    # ... existing setup ...

    kb_id = os.getenv("KB_ID")  # Set via template.yaml env var

    # [NEW] If query looks like a definition/FAQ, try KB first
    if kb_id and any(k in clean_q.lower() for k in ["what is", "what does", "explain", "how is"]):
        kb_answer = _query_knowledge_base(kb_id, clean_q)
        if kb_answer:
            # Return early with KB answer (no planning needed)
            return {
                "plan": "Retrieved from Knowledge Base (FAQ)",
                "actions": [{"tool": "knowledge_base", "args": {"query": clean_q}, "result": {"answer": kb_answer}}],
                "verify": {"ok": True, "notes": "kb_retrieval"},
                "answer": {"summary": kb_answer, "source": "RentPilot FAQ (CMHC Knowledge Base)"},
                "meta": {"model_id": model_id, "agent_version": agent_version, "kb_id": kb_id}
            }

    # ... rest of existing run_agent logic ...
```

#### 5d. Update template.yaml Environment

```yaml
AgentHandlerFn:
  Environment:
    Variables:
      # ... existing vars ...
      KB_ID: "KB12345XYZ"  # Replace with your actual Knowledge Base ID
```

### 6. Redeploy and Test

```bash
sam build
sam deploy

# Test KB-enabled query
curl -X POST https://YOUR_API_URL/agent \
  -H "Content-Type: application/json" \
  -d '{"query": "What is CMHC?"}'
```

Expected response:
```json
{
  "plan": "Retrieved from Knowledge Base (FAQ)",
  "actions": [
    {
      "tool": "knowledge_base",
      "args": {"query": "What is CMHC?"},
      "result": {"answer": "CMHC stands for Canada Mortgage and Housing Corporation..."}
    }
  ],
  "verify": {"ok": true, "notes": "kb_retrieval"},
  "answer": {
    "summary": "CMHC stands for Canada Mortgage and Housing Corporation...",
    "source": "RentPilot FAQ (CMHC Knowledge Base)"
  },
  "meta": {"model_id": "...", "agent_version": "v2-bedrock", "kb_id": "KB12345XYZ"}
}
```

---

## Alternative AgentCore Primitives

### Option 2: Action Groups

- **What**: Register Lambda tools as AgentCore Action Groups
- **How**: Use `bedrock-agent` API to create agent + action groups
- **Benefit**: Bedrock handles tool orchestration (vs DIY policy.py)
- **Downside**: More setup; less transparent for demo

### Option 3: Guardrails

- **What**: Add PII redaction or content filtering
- **How**: Create a Bedrock Guardrail, attach to Converse call
- **Benefit**: Demonstrates security/compliance awareness
- **Example**:
  ```python
  resp = BEDROCK.converse(
      modelId=model_id,
      messages=[...],
      guardrailConfig={
          "guardrailIdentifier": "gr-abc123",
          "guardrailVersion": "1"
      }
  )
  ```

---

## Cost Estimate (Knowledge Base)

| Component | Cost | Notes |
|-----------|------|-------|
| **Titan Embeddings** | ~$0.10/million tokens | One-time ingestion (~1K tokens for FAQ) → <$0.01 |
| **OpenSearch Serverless** | ~$0.24/OCU-hour | 2 OCUs (min) × 24h × 30d → ~$350/mo (⚠️ expensive) |
| **Retrieval API** | ~$0.01/1K queries | Cheap |

**Recommendation**: Use **Aurora PostgreSQL with pgvector** instead of OpenSearch Serverless to save costs (~$25/mo vs $350/mo).

---

## Testing Checklist

- [ ] Knowledge Base ingests FAQ successfully
- [ ] `retrieve-and-generate` returns correct answer for "What is CMHC?"
- [ ] Agent API returns KB answer (not planning) for FAQ queries
- [ ] Non-FAQ queries still use planning → tools → finalize flow
- [ ] Ledger captures KB retrieval as action

---

## Architecture Trade-offs

RentPilot's current design prioritizes:
- **Transparency**: Judges can trace exact tool invocations without black-box orchestration
- **Simplicity**: No vector store setup or embeddings model required
- **Determinism**: Verification logic is fully inspectable in `agent_bedrock.py`

Adding AgentCore primitives would enable:
- **Knowledge Base**: FAQ retrieval for common questions (e.g., "What is CMHC?")
- **Action Groups**: Bedrock-managed tool orchestration instead of `policy.py`
- **Guardrails**: Built-in PII redaction and content filtering

Both approaches are valid for the hackathon. The current implementation emphasizes code clarity for judge evaluation.

---

## References

- [Bedrock Knowledge Bases Docs](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base.html)
- [Bedrock Agent Runtime API](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_RetrieveAndGenerate.html)
- [OpenSearch Serverless Pricing](https://aws.amazon.com/opensearch-service/pricing/)
- [Aurora Serverless v2 Pricing](https://aws.amazon.com/rds/aurora/pricing/)

---

## Contact

For AgentCore integration questions, please open a GitHub issue with the label `agentcore`.
