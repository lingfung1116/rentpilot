# lambdas/agent_handler.py
import json
import os

import agent_bedrock

CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
}

def _resp(status, body):
    return {"statusCode": status, "headers": CORS_HEADERS, "body": json.dumps(body, ensure_ascii=False)}

def lambda_handler(event, context):
    # Preflight
    if (event.get("httpMethod") or event.get("requestContext", {}).get("http", {}).get("method")) == "OPTIONS":
        return _resp(200, {"ok": True})

    try:
        raw = event.get("body") or "{}"
        if event.get("isBase64Encoded"):  # rarely set by API GW, but safe
            import base64
            raw = base64.b64decode(raw).decode("utf-8", "ignore")
        data = json.loads(raw) if isinstance(raw, str) else (raw or {})
        query = (data.get("query") or "").strip()
        if not query:
            return _resp(400, {"error": "Missing 'query' in JSON body"})

        env = agent_bedrock.run_agent(query, print_blocks=False, show_json=True, no_ledger=False)
        return _resp(200, env)
    except Exception as e:
        # Log error for CloudWatch debugging (judges can inspect logs)
        print(f"ERROR in agent_handler: {e}")
        # include CORS on errors too
        return _resp(500, {"error": str(e)})
