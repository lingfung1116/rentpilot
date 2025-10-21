# lambdas/test_tools.py
import json
from typing import Any, Dict

from lambdas.evaluate_rent_affordability import lambda_handler as afford
from lambdas.get_neighbourhood_stats import lambda_handler as get_stats
# Import your actual tool handlers
from lambdas.get_rent_data import lambda_handler as get_rent
from lambdas.suggest_neighbourhoods import lambda_handler as suggest


def _resp(status: int, obj: Dict[str, Any]):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(obj, ensure_ascii=False)
    }

def lambda_handler(event, context):
    try:
        results = []

        # 1) City-level median (no neighbourhoods to keep it fast)
        r = get_rent({"city": "Toronto", "property_type": "1bed", "include_neighbourhoods": False}, None)
        ok_r = r.get("statusCode") == 200
        results.append({"tool": "get_rent_data", "ok": ok_r})

        # 2) Neighbourhood stats (ensure list present)
        s = get_stats({"city": "Toronto", "property_type": "1bed"}, None)
        try:
            s_body = json.loads(s["body"]) if isinstance(s.get("body"), str) else s.get("body", {})
        except Exception:
            s_body = {}
        ok_s = (s.get("statusCode") == 200 and isinstance(s_body.get("neighbourhoods"), list))
        results.append({"tool": "get_neighbourhood_stats", "ok": ok_s})

        # 3) Suggestions (shape only)
        sg = suggest({
            "city": "Toronto",
            "property_type": "1bed",
            "income_annual": 80000,
            "prefs": {"max_distance_km": 12, "min_transit": 60, "target_rent_to_income": 0.30},
            "budget_cap": 2200
        }, None)
        ok_sg = sg.get("statusCode") == 200
        results.append({"tool": "suggest_neighbourhoods", "ok": ok_sg})

        # 4) Affordability math (shape only)
        af = afford({
            "listing_price": 2000,
            "city_median": 1900,
            "income_annual": 72000,
            "target_ratio": 0.30
        }, None)
        ok_af = af.get("statusCode") == 200
        results.append({"tool": "evaluate_rent_affordability", "ok": ok_af})

        return _resp(200, {"ok": all(x["ok"] for x in results), "results": results})

    except Exception as e:
        return _resp(500, {"ok": False, "error": "internal_error", "reason": str(e)})
