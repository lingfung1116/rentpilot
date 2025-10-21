# agent_bedrock.py
# -----------------------------------------------------------------------------
# RentPilot — Bedrock Orchestrator (UI + Lambda friendly)
#
# What this script does:
#   1) Accept a user query (supports inline args with ":: key=value" and "prefs={...}").
#   2) Ask Bedrock (Claude/Llama) for a STRICT-JSON planning object: {plan, actions}.
#   3) Execute deterministically via policy.decide_and_act(clean_q, enriched_args).
#   4) Ask Bedrock to draft a concise human-facing ANSWER using the tool result.
#   5) Apply a local verify pass (deterministic), then write step/entry to ledger.
#
# Highlights for judges:
#   - Clean JSON envelope: {plan, actions, verify, answer, meta}
#   - Transparent planning → tools → finalize → verify pipeline
#   - Prompts are externalizable (prompts/*.txt) for easy humanizing, with safe fallback
#   - Defaults and verify behavior configurable via env (no hard-coded tuning)
#
# Env (examples):
#   export AWS_REGION=us-east-1
#   export MODEL_ID="anthropic.claude-3-sonnet-20240229-v1:0"
#   export LEDGER_LOCAL_ENABLE=1
#   export LEDGER_LOCAL_PATH="/tmp/ledger.jsonl"
#   export LEDGER_S3_BUCKET="rentpilot-artifacts"
#   export LEDGER_S3_PREFIX="ledger/"
#   export LEDGER_SESSION_ID="demo-bedrock-001"
#   export AGENT_VERSION="v2-bedrock"
#   export PROMPT_DIR="prompts"
#   export RP_PREFS_DEFAULT='{"max_distance_km": 12, "min_transit": 60, "target_rent_to_income": 0.30}'
#   export RP_VERIFY_STRICT=1
#   export RP_VERIFY_HINTS=1
# -----------------------------------------------------------------------------

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import boto3

import policy
from ledger import write_entry, write_step

# ----------------------------- Config & Clients -----------------------------
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
BEDROCK = boto3.client("bedrock-runtime", region_name=AWS_REGION)

# Token caps to keep demos snappy and costs predictable
_MAX_TOK_PLANNING = int(os.getenv("PLANNING_MAX_TOKENS", "700"))
_MAX_TOK_FINALIZE = int(os.getenv("FINALIZE_MAX_TOKENS", "600"))

# ---- Prompt configuration ----
PROMPT_DIR = os.getenv("PROMPT_DIR", "prompts")
PLANNING_PROMPT_PATH = os.getenv("PLANNING_PROMPT_PATH", os.path.join(PROMPT_DIR, "planning.txt"))
FINALIZE_PROMPT_PATH = os.getenv("FINALIZE_PROMPT_PATH", os.path.join(PROMPT_DIR, "finalize.txt"))

def _load_text(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None

# Default prefs from env JSON (null disables that constraint)
_RP_PREFS_DEFAULT = os.getenv(
    "RP_PREFS_DEFAULT",
    '{"max_distance_km": 12, "min_transit": 60, "target_rent_to_income": 0.30}'
)
try:
    _DEFAULT_PREFS = json.loads(_RP_PREFS_DEFAULT)
    if not isinstance(_DEFAULT_PREFS, dict):
        _DEFAULT_PREFS = {}
except Exception:
    _DEFAULT_PREFS = {"max_distance_km": 12, "min_transit": 60, "target_rent_to_income": 0.30}

RP_VERIFY_STRICT = os.getenv("RP_VERIFY_STRICT", "1") == "1"
RP_VERIFY_HINTS  = os.getenv("RP_VERIFY_HINTS",  "1") == "1"

# ----------------------------- Arg parsing & tiny NLU -----------------------------
_CITIES = [
    "Toronto","Montreal","Vancouver","Ottawa","Calgary","Edmonton",
    "Winnipeg","Quebec City","Hamilton","Mississauga","Brampton","Markham",
]
_PROP_MAP = {
    r"\b(studio|bachelor)\b": "studio",
    r"\b(1[\s-]*bed|one[\s-]*bed(room)?)\b": "1bed",
    r"\b(2[\s-]*bed|two[\s-]*bed(room)?)\b": "2bed",
    r"\b(3[\s-]*bed|three[\s-]*bed(room)?)\b": "3bed",
}

def _lenient_json_parse(obj_like: str) -> Optional[Dict[str, Any]]:
    """
    Accepts loose dict-like strings: {min_transit:90, target_rent_to_income:0.33}
    Converts to valid JSON and parses; returns None on failure.
    """
    try:
        s = obj_like.strip()
        if not (s.startswith("{") and s.endswith("}")):
            return None
        # Quote bare keys:  foo: -> "foo":
        s = re.sub(r'([{,]\s*)([A-Za-z_][A-Za-z0-9_\-]*)(\s*:)', r'\1"\2"\3', s)
        # Replace single quotes with double quotes
        s = s.replace("'", '"')
        return json.loads(s)
    except Exception:
        return None

def _parse_inline_args(q: str) -> Tuple[str, Dict[str, Any]]:
    """
    Parse ':: key=value key=value' tail, returning (stripped_query, args_dict).
    Supports prefs={...} where {...} can be lenient JSON.
    """
    args: Dict[str, Any] = {}
    if "::" not in q:
        return q.strip(), args

    q_head, tail = q.split("::", 1)
    # Try to grab a full prefs blob first (to avoid splitting inside braces)
    m = re.search(r"prefs\s*=\s*(\{.*\})", tail)
    prefs_blob = m.group(1) if m else None
    if prefs_blob:
        parsed = _lenient_json_parse(prefs_blob)
        if isinstance(parsed, dict):
            args["prefs"] = parsed
        # remove the prefs blob from tail so remaining tokens split cleanly
        tail = tail.replace(f"prefs={prefs_blob}", "")

    for token in tail.strip().split():
        if "=" not in token:
            continue
        k, v = token.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k == "prefs":
            # if we didn't catch it via blob above, attempt one-token parse
            parsed = _lenient_json_parse(v)
            if isinstance(parsed, dict):
                args["prefs"] = parsed
            continue
        # Try float
        try:
            vv: Any = float(v) if v.replace(".", "", 1).isdigit() else v
        except Exception:
            vv = v
        args[k] = vv

    return q_head.strip(), args

def _auto_args_from_text(user_text: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Fill missing {city, property_type} by scanning free text; explicit args win."""
    text = user_text.lower()
    out = dict(args)

    if "city" not in out:
        for c in _CITIES:
            if c.lower() in text:
                out["city"] = c
                break

    if "property_type" not in out:
        for pat, norm in _PROP_MAP.items():
            if re.search(pat, text, re.IGNORECASE):
                out["property_type"] = norm
                break

    return out

def _normalize_prefs(enriched_args: Dict[str, Any]) -> None:
    """
    Merge user prefs with env defaults; allow `null` (or None) to disable a constraint.
    Accepts prefs as dict or string (lenient JSON).
    """
    prefs_in = enriched_args.get("prefs") or {}
    if isinstance(prefs_in, str):
        prefs_in = _lenient_json_parse(prefs_in) or {}
    # start with defaults
    prefs: Dict[str, Any] = {}
    for k, v in _DEFAULT_PREFS.items():
        if v is not None:
            prefs[k] = v
    # overlay user prefs (explicit None removes key)
    for k, v in (prefs_in or {}).items():
        if v is None and k in prefs:
            del prefs[k]
        else:
            prefs[k] = v
    enriched_args["prefs"] = prefs

# ----------------------------- Verify helper (configurable) -----------------------------
def _local_verify(result: Dict[str, Any]) -> Dict[str, Any]:
    if not RP_VERIFY_STRICT:
        return result.get("verify") or {"ok": True}

    v = result.get("verify") or {}
    ans = result.get("answer") or {}
    actions = result.get("actions") or []
    first_tool = actions[0]["tool"] if (actions and isinstance(actions, list) and len(actions) > 0) else None

    # Try to locate prefs used
    prefs: Dict[str, Any] = {}
    tr = result.get("tool_result") or {}
    if isinstance(tr, dict):
        args = tr.get("args") if isinstance(tr.get("args"), dict) else {}
        prefs = args.get("prefs") if isinstance(args, dict) else {}
    if not prefs and isinstance(ans, dict):
        prefs = ans.get("prefs") or {}

    # Suggest flow: require recommendations list
    if first_tool == "suggest_neighbourhoods":
        recs = []
        if isinstance(ans, dict):
            recs = ans.get("recommendations") or []
        if not recs and isinstance(tr, dict):
            tr_ans = tr.get("answer") or {}
            if isinstance(tr_ans, dict):
                recs = tr_ans.get("recommendations") or []
        if not recs:
            if RP_VERIFY_HINTS:
                hints: List[str] = []
                md = prefs.get("max_distance_km")
                if md is not None and md <= 12:
                    hints.append(f"Try increasing max_distance_km from {md} → {md+3}")
                mt = prefs.get("min_transit")
                if mt is not None and mt >= 60:
                    hints.append(f"Consider lowering min_transit from {mt} → {max(mt-5,0)}")
                tri = prefs.get("target_rent_to_income")
                if tri is not None and tri <= 0.30:
                    hints.append(f"Consider raising target_rent_to_income from {tri:.2f} → {min(tri+0.03,0.4):.2f}")
                return {"ok": False, "reasons": ["No neighborhoods matched the specified criteria"] + hints[:2]}
            return {"ok": False, "reasons": ["No neighborhoods matched the specified criteria"]}

    # Affordability sanity (only if fields exist)
    try:
        if isinstance(ans, dict):
            lp = ans.get("listing_price")
            inc = ans.get("income_annual")
            tgt = ans.get("target_ratio")
            if lp is not None and inc is not None and tgt is not None:
                lp, inc, tgt = float(lp), float(inc), float(tgt)
                if 0 < tgt < 1.0:
                    monthly_income = inc / 12.0
                    if lp > monthly_income * (tgt * 1.25):
                        return {"ok": False, "notes": "Listing far above target ratio; consider increasing budget or relaxing constraints."}
    except Exception:
        pass

    return v or {"ok": True}

# ----------------------------- Prompts & Bedrock calls -----------------------------
def _system_prompt_planning() -> str:
    """
    Prefer a humanized prompt from file; fallback to strict JSON prompt.
    """
    txt = _load_text(PLANNING_PROMPT_PATH)
    if txt:
        return txt
    return (
        "You are RentPilot Orchestrator.\n"
        "Speak to the planner like a teammate—brief and clear—but output MUST be strict JSON.\n"
        "Return ONLY:\n"
        "{ \"plan\": <string>,\n"
        "  \"actions\": [ { \"tool\": \"get_rent_data\"|\"get_neighbourhood_stats\"|"
        "\"suggest_neighbourhoods\"|\"evaluate_rent_affordability\",\n"
        "                 \"args\": <object matching tool schema> } ... ] }\n"
        "\n"
        "Schemas:\n"
        "- get_rent_data.args: { \"city\": <string>, \"property_type\": <\"studio\"|\"1bed\"|\"2bed\"|\"3bed\"> }\n"
        "- get_neighbourhood_stats.args: { \"city\": <string>, \"property_type\": <string> }\n"
        "- suggest_neighbourhoods.args: {\n"
        "    \"city\": <string>, \"property_type\": <string>, \"income_annual\": <number>,\n"
        "    \"prefs\": { \"max_distance_km\": <number|null>, \"min_transit\": <number|null>, \"target_rent_to_income\": <0..1|null> },\n"
        "    \"budget_cap\": <number|null>\n"
        "  }\n"
        "- evaluate_rent_affordability.args: {\n"
        "    \"listing_price\": <number>, \"city_median\": <number>,\n"
        "    \"income_annual\": <number>, \"target_ratio\": <0..1>\n"
        "  }\n"
        "Rules: Keep actions minimal. Use provided fields only. JSON only—no prose."
    )

def _system_prompt_finalize() -> str:
    """
    Prefer a humanized prompt from file; fallback to strict finalize prompt.
    """
    txt = _load_text(FINALIZE_PROMPT_PATH)
    if txt:
        return txt
    return (
        "You are RentPilot Presenter.\n"
        "Given tool_results, produce ONLY JSON with keys: plan, actions, verify, answer.\n"
        "- Make the summary concise, friendly, and plain English.\n"
        "- Do not invent data; summarize exactly what tools returned.\n"
        "- JSON only, no extra text."
    )

def _converse_json(client, *, model_id: str, system_text: str, user_text: str, max_tokens: int) -> str:
    """
    Bedrock Converse with top-level 'system' and single 'user' turn.
    Returns concatenated text from content blocks.
    """
    resp = client.converse(
        modelId=model_id,
        system=[{"text": system_text}],
        messages=[{"role": "user", "content": [{"text": user_text}]}],
        inferenceConfig={"maxTokens": max_tokens, "temperature": 0.2, "topP": 0.95},
    )
    content = resp.get("output", {}).get("message", {}).get("content", [])
    return "".join([c.get("text", "") for c in content if isinstance(c, dict)])

# ----------------------------- Robust JSON extraction -----------------------------
def _extract_first_json(text: str) -> Optional[str]:
    """
    Best-effort: find the first top-level {...} JSON object in text.
    Handles code fences and leading/trailing prose.
    Returns the substring or None.
    """
    if not text:
        return None
    t = text.strip()
    # remove triple backtick fences if present
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.IGNORECASE | re.DOTALL).strip()
    # quick path
    if t.startswith("{") and t.endswith("}"):
        try:
            json.loads(t)
            return t
        except Exception:
            pass
    # scan for first balanced object
    starts = [m.start() for m in re.finditer(r"\{", t)]
    for s in starts:
        depth = 0
        for i, ch in enumerate(t[s:], s):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    cand = t[s:i+1]
                    try:
                        json.loads(cand)
                        return cand
                    except Exception:
                        break
    return None

# ----------------------------- Planning & Finalize wrappers -----------------------------
def _converse_plan(model_id: str, clean_query: str, enriched_args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ask the model for a {plan, actions} JSON. Provide both the query and the parsed args.
    """
    user_payload = {"query": clean_query, "args": enriched_args}
    text = _converse_json(
        BEDROCK,
        model_id=model_id,
        system_text=_system_prompt_planning(),
        user_text=json.dumps(user_payload, ensure_ascii=False),
        max_tokens=_MAX_TOK_PLANNING,
    )
    candidate = _extract_first_json(text) or text
    try:
        data = json.loads(candidate)
        if not isinstance(data.get("actions", []), list):
            data["actions"] = []
        if "plan" not in data:
            data["plan"] = "No plan returned"
        return data
    except Exception:
        return {"plan": f"(unparsed) {text[:2000]}", "actions": []}

def _converse_finalize(model_id: str, clean_query: str, plan: str, actions: List[Dict[str, Any]], tool_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Provide the actual tool result to the model and ask it to craft a clean ANSWER.
    Preserve the JSON envelope. Keep tool_result echoed for verify alignment.
    """
    user_payload = {
        "query": clean_query,
        "plan": plan,
        "actions": actions,
        "tool_result": tool_result
    }
    text = _converse_json(
        BEDROCK,
        model_id=model_id,
        system_text=_system_prompt_finalize(),
        user_text=json.dumps(user_payload, ensure_ascii=False),
        max_tokens=_MAX_TOK_FINALIZE,
    )
    candidate = _extract_first_json(text) or text
    try:
        data = json.loads(candidate)
        pack = {
            "plan": data.get("plan", plan),
            "actions": data.get("actions", actions),
            "verify": data.get("verify"),
            "answer": data.get("answer") or {"message": "See tool_result"},
            "tool_result": tool_result,
        }
        # Coerce verify to dict
        if not isinstance(pack["verify"], dict):
            pack["verify"] = {}
        return pack
    except Exception:
        return {
            "plan": plan,
            "actions": actions,
            "verify": {"ok": True, "notes": "Finalize parse fallback"},
            "answer": {"summary": "Summary based on tools", "message": "Summary based on tools"},
            "tool_result": tool_result,
        }

# ----------------------------- Orchestrator -----------------------------
def run_agent(user_input: str, *, print_blocks: bool = True, show_json: bool = False, no_ledger: bool = False) -> Dict[str, Any]:
    """
    Full loop: planning → tools → finalize → verify → ledger.
    Returns the final structured dict.
    """
    # Session & model
    session_id = os.getenv("LEDGER_SESSION_ID") or "demo-bedrock-session"
    agent_version = os.getenv("AGENT_VERSION", "v2-bedrock")
    model_id = os.getenv("MODEL_ID", "anthropic.claude-3-sonnet-20240229-v1:0")

    # 1) Parse + enrich args
    clean_q, inline_args = _parse_inline_args(user_input)
    enriched_args = _auto_args_from_text(clean_q, inline_args)
    _normalize_prefs(enriched_args)

    # 2) Planning
    plan_pack = _converse_plan(model_id, clean_q, enriched_args)
    if not no_ledger:
        write_step(
            user_query=clean_q, stage="planning",
            payload={"model_id": model_id, "plan": plan_pack.get("plan"), "actions": plan_pack.get("actions")},
            session_id=session_id, agent_version=agent_version, model_id=model_id
        )

    # 3) Execute tools via local policy (deterministic)
    if not no_ledger:
        write_step(
            user_query=clean_q, stage="tool_execute",
            payload={"args": enriched_args},
            session_id=session_id, agent_version=agent_version, model_id=model_id
        )
    tool_result = policy.decide_and_act(clean_q, enriched_args)

    # 4) Finalize
    final_pack = _converse_finalize(
        model_id=model_id,
        clean_query=clean_q,
        plan=plan_pack.get("plan", ""),
        actions=plan_pack.get("actions", []),
        tool_result=tool_result,
    )

    # [NEW] Promote recommendations from tool_result if the model omitted them
    try:
        tr_recs = (((tool_result or {}).get("answer") or {}).get("recommendations") or [])
        if tr_recs and isinstance(final_pack.get("answer"), dict) and not final_pack["answer"].get("recommendations"):
            final_pack["answer"]["recommendations"] = tr_recs
    except Exception:
        pass

    # 5) Local verify
    final_pack["verify"] = _local_verify(final_pack)

    # 6) Ledger
    if not no_ledger:
        write_step(
            user_query=clean_q, stage="finalize",
            payload=final_pack,
            session_id=session_id, agent_version=agent_version, model_id=model_id
        )
        entry_meta = write_entry(
            user_query=clean_q,
            args=enriched_args,
            result=final_pack,
            session_id=session_id,
            agent_version=agent_version,
            model_id=model_id,
        )
    else:
        entry_meta = {"ok": True, "local_path": None}

    # Console prints (useful for sam local / CLI)
    if print_blocks and not show_json:
        print("\n🧠 MODEL PLAN/ACTIONS (peek):")
        print(json.dumps({"plan": plan_pack.get("plan"), "actions": plan_pack.get("actions")}, indent=2, ensure_ascii=False))
        print("\n✅ RESULT SUMMARY:")
        print(json.dumps({k: final_pack[k] for k in ["plan","actions","verify","answer"] if k in final_pack}, indent=2, ensure_ascii=False))
        print("\n🪵 LEDGER ENTRY META:")
        print(json.dumps(entry_meta, indent=2, ensure_ascii=False))

    # Always include meta for UI
    final_pack.setdefault("meta", {"model_id": model_id, "agent_version": agent_version})

    if show_json:
        # CLI switch prints full envelope
        pass

    return final_pack

# ----------------------------- Tiny CLI -----------------------------
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="RentPilot + Bedrock Orchestrator")
    parser.add_argument("query", nargs="?", help="User query (supports ':: key=value' and 'prefs={...}')")
    parser.add_argument("--json", action="store_true", help="Print full JSON envelope only")
    args = parser.parse_args()

    if not args.query:
        print("Usage: python agent_bedrock.py \"median 1-bed rent in Toronto\" [--json]")
        raise SystemExit(2)

    env = run_agent(args.query, print_blocks=not args.json, show_json=args.json, no_ledger=False)
    if args.json:
        print(json.dumps(env, indent=2, ensure_ascii=False))
