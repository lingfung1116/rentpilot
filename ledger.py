# ledger.py
# Day-5: Local JSONL ledger with optional S3 mirroring + step logging.
# Records a canonical line per interaction and lightweight step breadcrumbs.
#
# Env:
#   LEDGER_LOCAL_ENABLE=1                 (default 1)
#   LEDGER_LOCAL_PATH="out/ledger.jsonl"  (default)
#   LEDGER_S3_BUCKET="your-bucket"        (optional to enable S3)
#   LEDGER_S3_PREFIX="ledger/"            (default)
#
# Typical usage:
#   from ledger import write_entry, write_step
#   write_step(user_query="...", stage="planning", payload={...}, session_id=..., agent_version="v1", model_id="...")
#   write_entry(user_query="...", args={...}, result={...}, session_id=..., agent_version="v1", model_id="...")

import json
import os
import time
import uuid
from typing import Any, Dict, Optional

# -------- Local JSONL config --------
_LOCAL_PATH = os.getenv("LEDGER_LOCAL_PATH", "out/ledger.jsonl")
_ENABLE_LOCAL = os.getenv("LEDGER_LOCAL_ENABLE", "1") == "1"

def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def _ensure_dir(path: str):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

def write_entry(
    *,
    user_query: str,
    args: Dict[str, Any],
    result: Dict[str, Any],
    session_id: Optional[str] = None,
    agent_version: str = "v1",
    model_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Canonical one-line record capturing plan/actions/verify/answer for a single interaction.
    """
    rec: Dict[str, Any] = {
        "ts": _now_iso(),
        "session_id": session_id or str(uuid.uuid4()),
        "agent_version": agent_version,
        "model_id": model_id,
        "user_query": user_query,
        "args": args,
        "plan": result.get("plan"),
        "actions": result.get("actions"),
        "verify": result.get("verify"),
        "answer": result.get("answer"),
    }
    out: Dict[str, Any] = {"ok": True, "local_path": None}

    if _ENABLE_LOCAL:
        try:
            _ensure_dir(_LOCAL_PATH)
            with open(_LOCAL_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out["local_path"] = _LOCAL_PATH
        except Exception as e:
            out.update({"ok": False, "local_error": str(e)})

    # Also mirror to S3 if configured (best-effort; don't fail on S3 errors)
    s3_out = write_entry_s3(rec)
    if s3_out.get("ok"):
        out["s3_uri"] = s3_out.get("s3_uri")
    elif s3_out.get("s3_error"):
        # S3 failed but local succeeded - still return ok=True; log S3 error separately
        out["s3_error"] = s3_out.get("s3_error")

    return out

# -------- S3 mirroring & step logging --------
try:
    import boto3  # type: ignore
except Exception:
    boto3 = None  # allows local usage without boto3 installed

_S3_BUCKET = os.getenv("LEDGER_S3_BUCKET")
_S3_PREFIX = os.getenv("LEDGER_S3_PREFIX", "ledger/")
_ENABLE_S3 = bool(_S3_BUCKET) and (boto3 is not None)

def write_entry_s3(rec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Best-effort S3 write; returns status dict; never raises to caller.
    """
    out = {"ok": True, "s3_uri": None}
    if not _ENABLE_S3:
        return out
    try:
        key = f"{_S3_PREFIX}{rec['session_id']}/{rec['ts']}.json"
        body = json.dumps(rec, ensure_ascii=False).encode("utf-8")
        boto3.client("s3").put_object(Bucket=_S3_BUCKET, Key=key, Body=body)
        out["s3_uri"] = f"s3://{_S3_BUCKET}/{key}"
    except Exception as e:
        out.update({"ok": False, "s3_error": str(e)})
    return out

def write_step(
    *,
    user_query: str,
    stage: str,
    payload: Dict[str, Any],
    session_id: Optional[str] = None,
    agent_version: str = "v1",
    model_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Lightweight step logger to capture intermediate events (e.g., planning, tool_result, finalize).
    Useful for Day-5 judge transparency without changing your final response shape.
    """
    rec = {
        "ts": _now_iso(),
        "session_id": session_id or str(uuid.uuid4()),
        "agent_version": agent_version,
        "model_id": model_id,
        "user_query": user_query,
        "stage": stage,     # "planning" | "tool_result" | "finalize" | "verify" | etc.
        "payload": payload, # arbitrary dict (tool outputs, deltas, notes)
    }

    # Local append
    local_out = {"ok": True, "local_path": None}
    if _ENABLE_LOCAL:
        try:
            _ensure_dir(_LOCAL_PATH)
            with open(_LOCAL_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            local_out["local_path"] = _LOCAL_PATH
        except Exception as e:
            local_out = {"ok": False, "local_error": str(e)}

    # Optional S3 mirror
    s3_out = write_entry_s3(rec)
    return {"local": local_out, "s3": s3_out}
