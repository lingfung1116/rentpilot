# lambdas/test_health.py
import json
import os
import urllib.request
from typing import Any, Dict

_DATA_PATH = os.getenv("FTA_DATA_PATH", "data/neighbourhood_medians.json")
_DATA_URL  = os.getenv("FTA_DATA_URL")  # presigned S3 URL (optional)
LIVE_MODE  = os.getenv("LIVE_MODE", "0") == "1"

def _resp(status: int, obj: Dict[str, Any]):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(obj, ensure_ascii=False)
    }

def _load_json():
    if LIVE_MODE and _DATA_URL:
        with urllib.request.urlopen(_DATA_URL, timeout=3.0) as resp:
            if resp.status != 200:
                raise RuntimeError(f"DATA_URL HTTP {resp.status}")
            return json.loads(resp.read().decode("utf-8"))
    with open(_DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def lambda_handler(event, context):
    checks = []
    try:
        data = _load_json()
        checks.append({"name": "load_json", "ok": True})

        meta = data.get("meta", {}) or {}
        cities = list((data.get("cities", {}) or {}).keys())
        props = meta.get("property_types") or ["studio", "1bed", "2bed", "3bed"]

        checks.append({"name": "city_exists", "ok": bool(cities), "example_city": cities[0] if cities else None})
        checks.append({"name": "prop_supported", "ok": bool(props), "example_property_type": props[0] if props else None})

        return _resp(200, {
            "ok": all(c["ok"] for c in checks),
            "live_mode": LIVE_MODE,
            "dataset": {
                "snapshot_month": meta.get("snapshot_month"),
                "version": meta.get("version")
            },
            "checks": checks
        })
    except Exception as e:
        return _resp(500, {"ok": False, "error": "internal_error", "reason": str(e), "checks": checks})
