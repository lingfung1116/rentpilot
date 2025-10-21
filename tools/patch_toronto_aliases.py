# Read the three CMHC JSONs the user uploaded, list available zone names,
# and build a patched neighbourhood_medians.json using friendly names aliased
# to plausible CMHC zones with 1-bed values. Create output files and show paths.

import json
import re
from pathlib import Path

# Inputs (uploaded to the notebook environment)
base = Path("/mnt/data")
toronto_path = base / "toronto_112.json"
van_path = base / "Vancouver_112.json"
mtl_path = base / "Montreal_112.json"

def load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))

tor = load_json(toronto_path)
van = load_json(van_path)
mtl = load_json(mtl_path)

def zone_map(data):
    return {r["name"]: r for r in data.get("neighbourhoods", []) if isinstance(r.get("name"), str)}

tor_z = zone_map(tor)
van_z = zone_map(van)
mtl_z = zone_map(mtl)

# Show a quick sample of zone names for Vancouver / Montreal to guide mapping
van_names = sorted(list(van_z.keys()))[:40]
mtl_names = sorted(list(mtl_z.keys()))[:40]

# --- Friendly -> CMHC mappings (best-effort) ---

# Toronto mapping (from previous step; confident)
tor_mapping = {
    "Downtown Core": "Zone 1 - Toronto (Central)",
    "Liberty Village": "Zone 4 - Toronto (West)",
    "Midtown (Yonge–Eglinton)": "Zone 3 - Toronto (North)",
    "Etobicoke": "Etobicoke (Zones 5-7)",
    "North York": "North York (Zones 13-17)",
    "Scarborough": "Scarborough (Zones 10-12)",
}

# Try to locate suitable Vancouver / Montreal zone names heuristically:
# We'll search keys containing certain substrings; fall back to roll-ups if present.

def find_zone_like(zmap, *candidates):
    # Return the first zone containing any candidate substring (case-insensitive)
    keys = list(zmap.keys())
    for cand in candidates:
        c = cand.lower()
        for k in keys:
            if c in k.lower():
                return k
    return None

# Vancouver friendly names from user's original JSON
# We'll match to likely CMHC roll-ups or specific zones if they exist.
van_mapping = {}
van_mapping["Downtown"] = find_zone_like(van_z, "Downtown", "City of Vancouver (Downtown)") or \
                           find_zone_like(van_z, "Vancouver (West Side)")  # fallback
van_mapping["Kitsilano"] = find_zone_like(van_z, "Kitsilano", "Vancouver (West Side)")
van_mapping["Mount Pleasant"] = find_zone_like(van_z, "Mount Pleasant", "Vancouver (East Side)")
van_mapping["East Vancouver"] = find_zone_like(van_z, "Vancouver (East Side)", "Hastings", "Renfrew")
van_mapping["Burnaby Metrotown"] = find_zone_like(van_z, "Metrotown", "Burnaby")
van_mapping["Richmond City Centre"] = find_zone_like(van_z, "Richmond City Centre", "Richmond")

# Montreal friendly names from user's original JSON
mtl_mapping = {}
mtl_mapping["Ville-Marie (Downtown)"] = find_zone_like(mtl_z, "Ville-Marie", "Downtown", "Centre-ville", "Montreal (Centre)")
mtl_mapping["Griffintown"] = find_zone_like(mtl_z, "Griffintown", "Sud-Ouest", "Le Sud-Ouest")
mtl_mapping["Plateau-Mont-Royal"] = find_zone_like(mtl_z, "Plateau-Mont-Royal", "Plateau")
mtl_mapping["Outremont"] = find_zone_like(mtl_z, "Outremont")
mtl_mapping["Rosemont–La Petite-Patrie"] = find_zone_like(mtl_z, "Rosemont", "La Petite-Patrie")
mtl_mapping["Verdun"] = find_zone_like(mtl_z, "Verdun")

# Collect the chosen zones with their 1bed values (may be None if not found)
def extract_pairs(zmap, mapping):
    out = {}
    for friendly, zone in mapping.items():
        v = None
        if zone and zone in zmap:
            val = zmap[zone].get("1bed")
            v = float(val) if isinstance(val, (int, float)) else None
        out[friendly] = {"cmhc_zone": zone, "cmhc_1bed": v}
    return out

tor_pairs = extract_pairs(tor_z, tor_mapping)
van_pairs = extract_pairs(van_z, van_mapping)
mtl_pairs = extract_pairs(mtl_z, mtl_mapping)

# Build a patched neighbourhood_medians.json using the user's original schema and friendly names,
# but alias to CMHC zones and inject CMHC 1bed values.
project = {
    "meta": {
        "version": "static_json_v1",
        "currency": "CAD/month",
        "snapshot_month": "2024-10",
        "source": "CMHC Average Rent (Table 1.1.2)",
        "note": "Friendly names aliased to CMHC zones; 1-bed = CMHC Oct-24 average; transit/distance kept from seed where present."
    },
    "cities": {
        "Toronto": {
            "medians": {"studio": 2000, "1bed": 2500, "2bed": 3200},
            "neighbourhoods": [
                {"name": "Downtown Core", "alias_of": tor_pairs["Downtown Core"]["cmhc_zone"], "median": {"1bed": tor_pairs["Downtown Core"]["cmhc_1bed"]}, "transit": 95, "distance_km": 0.5, "source": "cmhc_alias"},
                {"name": "Liberty Village", "alias_of": tor_pairs["Liberty Village"]["cmhc_zone"], "median": {"1bed": tor_pairs["Liberty Village"]["cmhc_1bed"]}, "transit": 90, "distance_km": 2.5, "source": "cmhc_alias"},
                {"name": "Midtown (Yonge–Eglinton)", "alias_of": tor_pairs["Midtown (Yonge–Eglinton)"]["cmhc_zone"], "median": {"1bed": tor_pairs["Midtown (Yonge–Eglinton)"]["cmhc_1bed"]}, "transit": 88, "distance_km": 6.1, "source": "cmhc_alias"},
                {"name": "Etobicoke", "alias_of": tor_pairs["Etobicoke"]["cmhc_zone"], "median": {"1bed": tor_pairs["Etobicoke"]["cmhc_1bed"]}, "transit": 72, "distance_km": 9.8, "source": "cmhc_alias"},
                {"name": "North York", "alias_of": tor_pairs["North York"]["cmhc_zone"], "median": {"1bed": tor_pairs["North York"]["cmhc_1bed"]}, "transit": 80, "distance_km": 11.5, "source": "cmhc_alias"},
                {"name": "Scarborough", "alias_of": tor_pairs["Scarborough"]["cmhc_zone"], "median": {"1bed": tor_pairs["Scarborough"]["cmhc_1bed"]}, "transit": 70, "distance_km": 13.1, "source": "cmhc_alias"},
            ]
        },
        "Vancouver": {
            "medians": {"studio": 2100, "1bed": 2550, "2bed": 3300},
            "neighbourhoods": [
                {"name": "Downtown", "alias_of": van_pairs["Downtown"]["cmhc_zone"], "median": {"1bed": van_pairs["Downtown"]["cmhc_1bed"]}, "transit": 96, "distance_km": 0.5, "source": "cmhc_alias"},
                {"name": "Kitsilano", "alias_of": van_pairs["Kitsilano"]["cmhc_zone"], "median": {"1bed": van_pairs["Kitsilano"]["cmhc_1bed"]}, "transit": 83, "distance_km": 4.0, "source": "cmhc_alias"},
                {"name": "Mount Pleasant", "alias_of": van_pairs["Mount Pleasant"]["cmhc_zone"], "median": {"1bed": van_pairs["Mount Pleasant"]["cmhc_1bed"]}, "transit": 85, "distance_km": 3.0, "source": "cmhc_alias"},
                {"name": "East Vancouver", "alias_of": van_pairs["East Vancouver"]["cmhc_zone"], "median": {"1bed": van_pairs["East Vancouver"]["cmhc_1bed"]}, "transit": 80, "distance_km": 5.5, "source": "cmhc_alias"},
                {"name": "Burnaby Metrotown", "alias_of": van_pairs["Burnaby Metrotown"]["cmhc_zone"], "median": {"1bed": van_pairs["Burnaby Metrotown"]["cmhc_1bed"]}, "transit": 82, "distance_km": 9.0, "source": "cmhc_alias"},
                {"name": "Richmond City Centre", "alias_of": van_pairs["Richmond City Centre"]["cmhc_zone"], "median": {"1bed": van_pairs["Richmond City Centre"]["cmhc_1bed"]}, "transit": 78, "distance_km": 12.0, "source": "cmhc_alias"},
            ]
        },
        "Montreal": {
            "medians": {"studio": 1600, "1bed": 1900, "2bed": 2400},
            "neighbourhoods": [
                {"name": "Ville-Marie (Downtown)", "alias_of": mtl_pairs["Ville-Marie (Downtown)"]["cmhc_zone"], "median": {"1bed": mtl_pairs["Ville-Marie (Downtown)"]["cmhc_1bed"]}, "transit": 95, "distance_km": 0.7, "source": "cmhc_alias"},
                {"name": "Griffintown", "alias_of": mtl_pairs["Griffintown"]["cmhc_zone"], "median": {"1bed": mtl_pairs["Griffintown"]["cmhc_1bed"]}, "transit": 90, "distance_km": 1.5, "source": "cmhc_alias"},
                {"name": "Plateau-Mont-Royal", "alias_of": mtl_pairs["Plateau-Mont-Royal"]["cmhc_zone"], "median": {"1bed": mtl_pairs["Plateau-Mont-Royal"]["cmhc_1bed"]}, "transit": 88, "distance_km": 2.0, "source": "cmhc_alias"},
                {"name": "Outremont", "alias_of": mtl_pairs["Outremont"]["cmhc_zone"], "median": {"1bed": mtl_pairs["Outremont"]["cmhc_1bed"]}, "transit": 86, "distance_km": 4.5, "source": "cmhc_alias"},
                {"name": "Rosemont–La Petite-Patrie", "alias_of": mtl_pairs["Rosemont–La Petite-Patrie"]["cmhc_zone"], "median": {"1bed": mtl_pairs["Rosemont–La Petite-Patrie"]["cmhc_1bed"]}, "transit": 83, "distance_km": 4.0, "source": "cmhc_alias"},
                {"name": "Verdun", "alias_of": mtl_pairs["Verdun"]["cmhc_zone"], "median": {"1bed": mtl_pairs["Verdun"]["cmhc_1bed"]}, "transit": 80, "distance_km": 6.0, "source": "cmhc_alias"},
            ]
        },
    }
}

# Write patched snapshot and also a per-city debug mapping for transparency
out_dir = base / "patched"
out_dir.mkdir(parents=True, exist_ok=True)

patched_path = out_dir / "neighbourhood_medians_patched.json"
patched_path.write_text(json.dumps(project, indent=2, ensure_ascii=False))

mappings_debug = {
    "Toronto": tor_pairs,
    "Vancouver": van_pairs,
    "Montreal": mtl_pairs,
    "Vancouver_zone_names_sample": sorted(list(van_z.keys()))[:60],
    "Montreal_zone_names_sample": sorted(list(mtl_z.keys()))[:60],
}
map_path = out_dir / "cmhc_alias_debug.json"
map_path.write_text(json.dumps(mappings_debug, indent=2, ensure_ascii=False))

print("Wrote:", str(patched_path))
print("Wrote:", str(map_path))
