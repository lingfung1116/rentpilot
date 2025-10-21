# providers/housing_data.py
# Single data-access layer for city/neighbourhood medians and transit scores.
# LIVE_MODE=0 -> internal JSON file at data/neighbourhood_medians.json
# LIVE_MODE=1 -> S3 JSON via presigned URL FTA_DATA_URL (still a snapshot; no public APIs)

import json
import os
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

_DATA_PATH = os.getenv("FTA_DATA_PATH", "data/Neighbourhood Medians Patching.json")
_DATA_URL  = os.getenv("FTA_DATA_URL")                 # presigned S3 URL (GET) when LIVE_MODE=1
LIVE_MODE  = os.getenv("LIVE_MODE", "0") == "1"

_SUPPORTED_PROPS = ("studio", "1bed", "2bed", "3bed")
_CACHE: Dict[str, Any] = {}  # in-process memo per Lambda invocation

def _load_json() -> Dict[str, Any]:
    if "dataset" in _CACHE:
        return _CACHE["dataset"]
    if LIVE_MODE and _DATA_URL:
        try:
            with urllib.request.urlopen(_DATA_URL, timeout=3.0) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"DATA_URL HTTP {resp.status}")
                data = json.loads(resp.read().decode("utf-8"))
                _CACHE["dataset"] = data
                return data
        except Exception as e:
            print(f"[WARN] Falling back to local JSON due to: {e}")

    with open(_DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        _CACHE["dataset"] = data
        return data

def city_key(city: str) -> str:
    return str(city or "").strip().title()

def supported_property_types() -> Tuple[str, ...]:
    return _SUPPORTED_PROPS

def get_meta() -> Dict[str, Any]:
    data = _load_json()
    return data.get("meta", {}) or {}

def get_city_obj(city: str) -> Optional[Dict[str, Any]]:
    data = _load_json()
    return (data.get("cities", {}) or {}).get(city_key(city))

def get_city_median(city: str, prop: str) -> Optional[float]:
    prop = (prop or "1bed").lower()
    city_obj = get_city_obj(city)
    if not city_obj:
        return None
    med = (city_obj.get("medians", {}) or {}).get(prop)
    try:
        return float(med) if med is not None else None
    except Exception:
        return None

def list_neighbourhoods(city: str) -> List[Dict[str, Any]]:
    city_obj = get_city_obj(city)
    if not city_obj:
        return []
    return (city_obj.get("neighbourhoods", []) or [])

def get_neighbourhood_median(row: Dict[str, Any], prop: str) -> Optional[float]:
    prop = (prop or "1bed").lower()
    med = (row.get("median", {}) or {}).get(prop)
    try:
        return float(med) if med is not None else None
    except Exception:
        return None

def normalize_transit(x: Any) -> Optional[int]:
    try:
        val = float(x)
    except Exception:
        return None
    if val != val:  # NaN
        return None
    val = max(0.0, min(100.0, val))
    return int(round(val))

def get_neighbourhood_transit(row: Dict[str, Any], default: int = 0) -> int:
    norm = normalize_transit(row.get("transit", default))
    if norm is None:
        return max(0, min(100, int(default)))
    return norm
