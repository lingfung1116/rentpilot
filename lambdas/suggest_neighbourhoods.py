import json
import os
from typing import Any, Dict, List

from providers.housing_data import (LIVE_MODE, city_key, get_city_obj,
                                    get_meta, get_neighbourhood_median,
                                    get_neighbourhood_transit,
                                    list_neighbourhoods)

_W_AFF = float(os.getenv("FTA_W_AFFORD", "0.5"))
_W_TRN = float(os.getenv("FTA_W_TRANSIT", "0.3"))
_W_DST = float(os.getenv("FTA_W_DIST", "0.2"))

def _safe_float(x, default=0.0) -> float:
    try:
        return float(x)
    except Exception:
        return float(default)

def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))

def _affordability_component(rti: float, target: float) -> float:
    if target <= 0:
        return 0.0
    over = max(0.0, rti - target)
    val = 1.0 - (over / max(target, 0.01))
    return max(0.0, min(1.0, val))

def _distance_component(distance_km: float, max_distance_km: float) -> float:
    if max_distance_km <= 0:
        return 0.0
    ratio = min(distance_km / max_distance_km, 1.0)
    return 1.0 - ratio

def _why(nei: Dict[str, Any], rent_diff: float, rti: float, prefs: Dict[str, Any]) -> str:
    msgs = []
    if rent_diff < 0:
        msgs.append(f"Cheaper by ${int(abs(rent_diff))}/mo")
    else:
        msgs.append(f"${int(rent_diff)}/mo above your price")
    min_transit = int(prefs.get("min_transit", 0))
    if int(nei.get("transit", 0)) >= min_transit:
        msgs.append(f"meets transit ≥{min_transit}")
    target = float(prefs.get("target_rent_to_income", 0.30))
    msgs.append("at or below {0}% RTI".format(int(target*100)) if rti <= target else f"near {int(target*100)}% target")
    return "; ".join(msgs) + "."

def lambda_handler(event, context):
    try:
        body = event if isinstance(event, dict) else {}
        if "body" in body and isinstance(body["body"], str):
            try:
                body = json.loads(body["body"])
            except Exception:
                body = {}

        city = city_key(body.get("city", "Toronto"))
        prop = (body.get("property_type", "1bed") or "1bed").lower()
        income_annual = _safe_float(body.get("income_annual"), 80000.0)

        prefs = body.get("prefs", {}) or {}
        max_dist = max(0.0, _safe_float(prefs.get("max_distance_km"), 15.0))
        min_transit = int(_clamp(_safe_float(prefs.get("min_transit", 65)), 0, 100))
        target_rti = _safe_float(prefs.get("target_rent_to_income"), 0.30)

        listing_price = body.get("listing_price")
        budget_cap = body.get("budget_cap")

        income_monthly = income_annual / 12.0
        price_ref = (_safe_float(listing_price)
                     if listing_price is not None
                     else _safe_float(budget_cap, round(income_monthly * target_rti, 2)))

        meta = get_meta()
        if not get_city_obj(city):
            return _resp(404, {"error": "city_not_found", "city": city})

        rows: List[Dict[str, Any]] = []
        for row in list_neighbourhoods(city):
            med = get_neighbourhood_median(row, prop)
            if med is None:
                continue

            transit = get_neighbourhood_transit(row, default=0)
            dist = max(0.0, _safe_float(row.get("distance_km", 0.0)))

            if dist > max_dist or transit < min_transit:
                continue

            rti = med / income_monthly if income_monthly > 0 else 1e9
            if rti > target_rti:
                continue

            aff = _affordability_component(rti, target_rti)
            transit_norm = max(0.0, min(1.0, transit / 100.0))
            dist_comp = _distance_component(dist, max_dist)
            score = (_W_AFF * aff) + (_W_TRN * transit_norm) + (_W_DST * dist_comp)

            rent_diff = med - price_ref
            rows.append({
                "name": row.get("name"),
                "median": med,
                "rent_diff_vs_listing": int(rent_diff),
                "rent_to_income": round(rti, 3),
                "transit": transit,
                "distance_km": dist,
                "score": round(score, 3),
                "why": _why(row, rent_diff, rti, prefs)
            })

        rows.sort(key=lambda x: x["score"], reverse=True)
        recs = rows[:3]

        payload = {
            "city": city,
            "property_type": prop,
            "source": meta.get("version", "static_json_v1"),
            "snapshot_month": meta.get("snapshot_month", "unknown"),
            "snapshot_fallback": True,
            "live_mode": LIVE_MODE,   # indicates internal vs S3 JSON path
            "recommendations": recs
        }
        if not recs:
            payload["reason"] = "no_neighbourhood_passed_filters"

        return _resp(200, payload)

    except Exception as e:
        return _resp(500, {"error": "internal_error", "reason": str(e)})

def _resp(status: int, obj: Dict[str, Any]):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(obj, ensure_ascii=False)
    }
