# Python 3.11 Lambda handler
# Purpose: compute affordability metrics and a human-readable verdict.
# Assumptions:
#  - Currency: CAD/month
#  - income_annual in CAD/year; we convert to monthly (divide by 12)
#  - target_ratio default 0.30
# Output example:
# {"delta_pct":0.04,"rti":0.39,"verdict":"Above market and above target ratio"}

import json
from typing import Any, Dict

# Named tolerances (readability; values match your original logic)
_MARKET_BAND = 0.02       # ±2% around city median counts as "near market"
_RATIO_TOL   = 0.02       # ±2% around target ratio counts as "near target"

def _safe_float(x, default=0.0) -> float:
    try:
        return float(x)
    except Exception:
        return float(default)

def lambda_handler(event, context):
    """
    event can be:
      - direct dict: {"listing_price":2600,"city_median":2500,"income_annual":80000,"target_ratio":0.30}
      - or API GW proxy with body string / queryStringParameters
    """
    try:
        body = event if isinstance(event, dict) else {}

        # also accept GET testing via queryStringParameters
        if "queryStringParameters" in body and isinstance(body["queryStringParameters"], dict):
            qs = body["queryStringParameters"]
            for k in ("listing_price", "city_median", "income_annual", "target_ratio"):
                body.setdefault(k, qs.get(k))

        # support POST body (proxy integration)
        if "body" in body and isinstance(body["body"], str):
            try:
                body = json.loads(body["body"])
            except Exception:
                body = {}

        listing = _safe_float(body.get("listing_price"))
        city_median = _safe_float(body.get("city_median"))
        income_annual = _safe_float(body.get("income_annual"))
        target_ratio = _safe_float(body.get("target_ratio"), 0.30)

        if listing <= 0 or city_median <= 0 or income_annual <= 0:
            return _resp(400, {
                "error": "invalid_input",
                "fields": {
                    "listing_price": listing,
                    "city_median": city_median,
                    "income_annual": income_annual
                }
            })

        delta_pct = (listing - city_median) / city_median  # e.g., +0.04 for +4%
        income_monthly = income_annual / 12.0
        rti = listing / income_monthly
        verdict = _make_verdict(delta_pct, rti, target_ratio)

        out = {
            "delta_pct": round(delta_pct, 4),
            "rti": round(rti, 4),
            "verdict": verdict
        }
        return _resp(200, out)

    except Exception as e:
        return _resp(500, {"error": "internal_error", "reason": str(e)})

def _make_verdict(delta_pct: float, rti: float, target_ratio: float) -> str:
    above_market = delta_pct > _MARKET_BAND
    below_market = delta_pct < -_MARKET_BAND
    near_market = not above_market and not below_market

    above_target = rti > (target_ratio + _RATIO_TOL)
    below_target = rti < (target_ratio - _RATIO_TOL)
    near_target  = not above_target and not below_target

    if above_market and above_target:
        return "Above market and above target ratio"
    if above_market and near_target:
        return "Above market; near target ratio"
    if near_market and above_target:
        return "Near market; above target ratio"
    if below_market and below_target:
        return "Below market and below target ratio"
    if below_market and near_target:
        return "Below market; near target ratio"
    if near_market and below_target:
        return "Near market; below target ratio"
    return "Near market and near target ratio"

def _resp(status: int, obj: Dict[str, Any]):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(obj, ensure_ascii=False)
    }
