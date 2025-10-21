# lambdas/get_neighbourhood_stats.py
# Purpose: Return neighbourhood-level stats (median, transit, distance_km)
# Source of truth: providers.housing_data (handles LIVE_MODE, S3 URL, local file)
import json
from typing import Any, Dict, List

from providers.housing_data import (LIVE_MODE, city_key, get_city_obj,
                                    get_meta, get_neighbourhood_median,
                                    get_neighbourhood_transit,
                                    list_neighbourhoods)


def _resp(status: int, obj: Dict[str, Any]):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(obj, ensure_ascii=False),
    }

def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return float(default)

def lambda_handler(event, context):
    """
    event:
      {"city":"Toronto","property_type":"1bed"}
    """
    try:
        # Parse
        body = event if isinstance(event, dict) else {}
        if "body" in body and isinstance(body["body"], str):
            try:
                body = json.loads(body["body"])
            except Exception:
                body = {}

        city = city_key(body.get("city", "Toronto"))
        prop = (body.get("property_type", "1bed") or "1bed").lower()

        # Data via provider (same path as other lambdas)
        meta = get_meta()
        city_obj = get_city_obj(city)
        if not city_obj:
            return _resp(404, {"error": "city_not_found", "city": city})

        rows: List[Dict[str, Any]] = []
        for row in list_neighbourhoods(city):
            m = get_neighbourhood_median(row, prop)
            if m is None:
                continue
            rows.append({
                "name": row.get("name"),
                "median": _safe_float(m),
                "transit": get_neighbourhood_transit(row, default=0),
                "distance_km": _safe_float(row.get("distance_km", 0.0)),
            })

        out = {
            "city": city,
            "property_type": prop,
            "currency": meta.get("currency", "CAD/month"),
            "snapshot_month": meta.get("snapshot_month", "unknown"),
            "source": meta.get("version", "static_json_v1"),
            "live_mode": LIVE_MODE,
            "neighbourhoods": rows,
        }
        return _resp(200, out)

    except Exception as e:
        return _resp(500, {"error": "internal_error", "reason": str(e)})

if __name__ == "__main__":
    print(lambda_handler({"city": "Toronto", "property_type": "1bed"}, None))
