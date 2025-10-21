# 🏠 RentPilot Agent

> **Bedrock-powered affordability advisor that plans, acts, verifies, and summarizes — fully serverless on AWS.**

[![AWS](https://img.shields.io/badge/AWS-Bedrock%20%7C%20Lambda%20%7C%20API%20Gateway-orange?logo=amazonaws)](https://aws.amazon.com/bedrock/)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

A transparent AI agent built for the **AWS AI Agent Global Hackathon** that helps renters find affordable housing in Canadian cities. RentPilot uses **Amazon Bedrock (Claude 3 Sonnet)** to orchestrate a deterministic pipeline: **plan → act → verify → summarize**, returning a strict machine-readable JSON envelope alongside a friendly human summary.

---

## 🎯 What It Does

RentPilot answers questions like:
- 💰 "What's the median 1-bed rent in Toronto?"
- ✅ "Is $2,200/month affordable on $80k income?"
- 🗺️ "Suggest neighbourhoods for me" (with transit, distance, affordability filters)

Instead of opaque "magic," it shows you:
1. **Plan**: What the agent decided to do
2. **Actions**: Which tools it called (city medians, neighbourhood stats, affordability calc)
3. **Verify**: Whether constraints were met (e.g., "No recommendations? Try relaxing filters")
4. **Answer**: Concise summary + structured data

All interactions are logged to a JSONL ledger (local + optional S3) for reproducibility.

---

## 💡 Why Bedrock?

| Feature | Benefit |
|---------|---------|
| **Converse API** | Native JSON mode, no brittle prompt engineering |
| **Serverless** | No infrastructure to manage; pay-per-invoke |
| **Transparent Planning** | Model drafts the plan; deterministic tools execute it |
| **Auditable** | Ledger captures every step (planning, tool calls, verification) |

---

## 🏗️ Architecture Overview

```
User Query (UI or CLI)
    ↓
API Gateway (/agent POST)
    ↓
Lambda (agent_handler.py)
    ↓
Bedrock Orchestrator (agent_bedrock.py)
    ├─→ [PLANNING] Bedrock Converse → {plan, actions}
    ├─→ [EXECUTE] Deterministic tools (policy.py + Lambda tools)
    ├─→ [FINALIZE] Bedrock Converse → human summary
    ├─→ [VERIFY] Local checks (recommendations? affordability sanity?)
    └─→ [LEDGER] Write JSONL + optional S3
    ↓
JSON Envelope Response:
{
  "plan": "...",
  "actions": [...],
  "verify": {...},
  "answer": {...},
  "meta": {...}
}
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed flow and diagram.

---

## 🚀 Quickstart

### Prerequisites
- AWS Account with Bedrock access (Claude 3 Sonnet)
- AWS SAM CLI installed
- Python 3.11+

### 1. Clone & Install
```bash
git clone <your-repo-url>
cd Devpost-rentpilot
pip install -r requirements.txt  # For local CLI usage
```

### 2. Deploy to AWS
```bash
sam build
sam deploy --guided
```

Follow the prompts (stack name, region, confirm IAM). Note the **AgentApiUrl** from outputs:
```
Outputs
-------
AgentApiUrl - https://abc123xyz.execute-api.us-east-1.amazonaws.com/prod/agent
```

### 3. Test the API
```bash
curl -X POST https://YOUR_API_URL/agent \
  -H "Content-Type: application/json" \
  -d '{"query": "median 1-bed rent in Toronto"}'
```

### 4. Host the UI (optional)
```bash
# Replace placeholder with your API URL
sed -i '' 's|YOUR_AGENT_API_URL|https://abc123xyz.execute-api.us-east-1.amazonaws.com/prod/agent|' demo_viewer.html

# Upload to S3 (static website hosting)
aws s3 mb s3://rentpilot-demo-ui
aws s3 cp demo_viewer.html s3://rentpilot-demo-ui/ --acl public-read
aws s3 website s3://rentpilot-demo-ui/ --index-document demo_viewer.html
```

Your UI will be at: `http://rentpilot-demo-ui.s3-website-us-east-1.amazonaws.com`

**UI Features**:
- 🎯 **Sample prompt buttons** for quick testing
- 📋 **Copy cURL** button for CLI testing
- ⚡ **Overlay spinner** during API calls
- 🔍 **Collapsible JSON envelope** viewer
- ⌨️ **Enter key** to submit queries

---

## 💻 Local CLI Usage

```bash
export AWS_REGION=us-east-1
export MODEL_ID="anthropic.claude-3-sonnet-20240229-v1:0"

# Simple query
python agent_bedrock.py "median 1-bed rent in Toronto"

# With inline args
python agent_bedrock.py "suggest areas :: city=Toronto property_type=1bed income_annual=80000"

# With prefs (JSON-like)
python agent_bedrock.py "suggest areas :: city=Toronto property_type=1bed income_annual=80000 prefs={min_transit:70,max_distance_km:10}"

# Full JSON output
python agent_bedrock.py "median 1-bed rent in Toronto" --json
```

---

## 📦 JSON Envelope Contract

All responses follow this **strict schema**:

```json
{
  "plan": "<string: what the agent decided to do>",
  "actions": [
    {
      "tool": "<get_rent_data | suggest_neighbourhoods | evaluate_rent_affordability>",
      "args": { ... },
      "result": { ... }
    }
  ],
  "verify": {
    "ok": true,
    "reasons": ["<optional hints if ok=false>"]
  },
  "answer": {
    "summary": "<concise human-friendly sentence>",
    "recommendations": [ ... ],  // if suggest_neighbourhoods
    "data": { ... }  // raw tool output
  },
  "meta": {
    "model_id": "anthropic.claude-3-sonnet-20240229-v1:0",
    "agent_version": "v2-bedrock"
  }
}
```

---

## 📝 Example Prompts

The UI includes **sample prompt buttons** for quick testing. Here are natural-language examples:

<details>
<summary><b>1. Quick Check (UI Sample Button)</b></summary>

**Query**:
```
Could you check the typical 1-bed rent in Toronto and whether $2,200/month makes sense on an $80k salary?
```

**Answer**: "A $2,200/month 1-bed rent in Toronto is affordable on an $80k salary, as it is below the city median of $2,500 and meets the 0.3 rent-to-income ratio target."

**Verify**: OK
</details>

<details>
<summary><b>2. Shortlist Areas (UI Sample Button)</b></summary>

**Query**:
```
Help me shortlist a few Toronto neighbourhoods for a 1-bed. Budget is about $2,200/month, within roughly 12 km of downtown, and I'd like decent transit (around 70+).
```

**Answer**: "The top 3 recommended Toronto neighborhoods for a 1-bed rental within your $2,200 budget and preferences are Downtown Core, Liberty Village, and Midtown (Yonge-Eglinton)."

**Verify**: OK
</details>

<details>
<summary><b>3. Explain the Math (UI Sample Button)</b></summary>

**Query**:
```
Before picking places, explain how you decide if a rent is affordable—for example, is $2,400/month reasonable on an $85k income?
```

**Answer**: "A rent of $2,400 per month is likely affordable on an $85,000 annual income based on the 30% rent-to-income guideline."

**Verify**: OK
</details>

<details>
<summary><b>4. Graceful Error Handling (UI Sample Button)</b></summary>

**Query**:
```
Try evaluating affordability with just a rent price so I can see your error handling.
```

**Answer**: "I cannot evaluate rent affordability without the required city, annual income, and target rent-to-income ratio inputs."

**Verify**: Not OK — Missing required inputs city, income_annual, and target_ratio to evaluate rent affordability.
</details>

### Advanced CLI Examples (with inline args)

<details>
<summary><b>5. Strict Filters → Verify with Hints</b></summary>

```bash
python agent_bedrock.py "suggest areas :: city=Toronto property_type=1bed income_annual=80000 prefs={min_transit:90,max_distance_km:5}"
```

**Verify**: If no results → `{ok: false, reasons: ["No neighbourhoods passed filters", "Try increasing max_distance_km from 5 → 8", "Consider lowering min_transit from 90 → 85"]}`
</details>

<details>
<summary><b>6. Budget Cap</b></summary>

```bash
python agent_bedrock.py "suggest areas :: city=Toronto property_type=1bed income_annual=80000 budget_cap=2000"
```

**Answer**: Filters neighbourhoods where median ≤ $2000/month
</details>

<details>
<summary><b>7. Lenient Prefs (relax ratio)</b></summary>

```bash
python agent_bedrock.py "suggest areas :: city=Vancouver property_type=studio income_annual=60000 prefs={target_rent_to_income:0.35}"
```

**Answer**: Allows up to 35% rent-to-income (default is 30%)
</details>

---

## 🌐 Live Mode (Optional S3 Dataset)

By default, RentPilot uses a static local JSON dataset (`data/Neighbourhood Medians Patching.json`). To switch to a live S3-hosted snapshot:

### 1. Upload Dataset to S3
```bash
aws s3 cp out/Neighbourhood-Medians-Oct2024.json s3://your-bucket/cmhc/
aws s3api put-object-acl --bucket your-bucket --key cmhc/Neighbourhood-Medians-Oct2024.json --acl public-read
```

### 2. Update `template.yaml`
```yaml
Environment:
  Variables:
    LIVE_MODE: "1"
    FTA_DATA_URL: "https://your-bucket.s3.us-east-1.amazonaws.com/cmhc/Neighbourhood-Medians-Oct2024.json"
```

### 3. Redeploy
```bash
sam build && sam deploy
```

The agent will fetch data from S3 on each Lambda cold start (with in-process caching).

---

## 📊 Ledger

Every interaction is logged to a JSONL file for **full reproducibility**:

- **Local CLI**: `out/ledger.jsonl` (default) or set `LEDGER_LOCAL_PATH`
- **Lambda**: `/tmp/ledger.jsonl` (ephemeral; survives warm containers)
- **Optional S3 Mirroring**: Uncomment S3 policy in `template.yaml`, set `LEDGER_S3_BUCKET` and `LEDGER_S3_PREFIX`

Each line is a JSON object:
```json
{
  "ts": "2025-10-19T12:34:56Z",
  "session_id": "demo-session-001",
  "agent_version": "v2-bedrock",
  "model_id": "anthropic.claude-3-sonnet-20240229-v1:0",
  "user_query": "suggest areas :: city=Toronto...",
  "args": {...},
  "plan": "...",
  "actions": [...],
  "verify": {...},
  "answer": {...}
}
```

---

## 📈 Data Provenance

| Aspect | Details |
|--------|---------|
| **Source** | Canada Mortgage and Housing Corporation (CMHC) Rental Market Survey, October 2024 |
| **Cities** | Toronto, Vancouver, Montreal (extensible) |
| **Property Types** | studio, 1bed, 2bed, 3bed |
| **Why Static JSON?** | CMHC doesn't offer a real-time API; we snapshot quarterly data |
| **Neighbourhood Medians** | Synthesized from CMHC zone data + patched with Toronto Open Data for transit scores |

---

## 🔒 Security & 💰 Cost Posture

### Security

| Aspect | Implementation |
|--------|----------------|
| **IAM** | Bedrock policy scoped to `foundation-model/*` in current region (no wildcard `*`) |
| **No PII Logging** | Queries are logged (income, property type), but no names/addresses |
| **CORS** | Enabled for demo UI; restrict `AllowOrigin` in production |
| **Secrets** | No hardcoded credentials; uses AWS IAM roles |

### Cost (per 1000 queries)

| Service | Cost Breakdown | Per Query |
|---------|----------------|-----------|
| **Bedrock (Claude 3 Sonnet)** | ~$0.003/1K input tokens, ~$0.015/1K output tokens | ~$0.02 |
| **Lambda** | 512MB @ 2s avg → ~$0.0000021/invoke | ~$0.002 |
| **API Gateway** | $3.50/million requests | ~$0.0035 |
| **Total** | | **~$0.026/1K queries** |

**Performance**: Cold start ~1.5s, warm <500ms

---

## 🤝 Contributing

This is a hackathon submission. For production use:
- Add authentication (API Gateway authorizer)
- Restrict CORS origins
- Add rate limiting (API Gateway usage plans)
- Implement caching (ElastiCache or DynamoDB)
- Add monitoring (CloudWatch dashboards, X-Ray tracing)

---

## 🙏 Acknowledgments

- **CMHC** for public rental market data
- **AWS Bedrock** for Claude 3 Sonnet access
- **Devpost** and AWS for hosting the AI Agent Global Hackathon

---

## 📧 Contact

For questions or feedback, please open an issue in this repository.

---

## 📄 License

MIT License (see LICENSE file if included, or specify your terms).
