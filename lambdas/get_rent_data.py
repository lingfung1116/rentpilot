import json
from typing import Any, Dict, List

from providers.housing_data import (LIVE_MODE, city_key, get_city_median,
                                    get_city_obj, get_meta,
                                    get_neighbourhood_median,
                                    get_neighbourhood_transit,
                                    list_neighbourhoods,
                                    supported_property_types)


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
        include_neigh = bool(body.get("include_neighbourhoods", True))

        meta = get_meta()
        city_obj = get_city_obj(city)
        if not city_obj:
            return _resp(404, {"error": "city_not_found", "city": city})

        city_median = get_city_median(city, prop)
        if city_median is None:
            return _resp(400, {
                "error": "unsupported_property_type",
                "property_type": prop,
                "supported": supported_property_types()
            })

        out: Dict[str, Any] = {
            "city": city,
            "property_type": prop,
            "median": city_median,
            "currency": meta.get("currency", "CAD/month"),
            "source": meta.get("version", "static_json_v1"),
            "snapshot_month": meta.get("snapshot_month", "unknown"),
            "snapshot_fallback": True,     # kept for compatibility in responses
            "live_mode": LIVE_MODE         # true if S3 URL path was used
        }

        if include_neigh:
            neighs: List[Dict[str, Any]] = []
            for row in list_neighbourhoods(city):
                m = get_neighbourhood_median(row, prop)
                if m is not None:
                    neighs.append({"name": row.get("name"), "median": m})
            out["neighbourhoods"] = neighs

        return _resp(200, out)

    except Exception as e:
        return _resp(500, {"error": "internal_error", "reason": str(e)})

def _resp(status: int, obj: Dict[str, Any]):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(obj, ensure_ascii=False)
    }
