# tools/merge_cmhc.py
import json
import pathlib
import re
import sys

USAGE = """
Usage:
  python tools/merge_cmhc.py out/cmhc_rental_medians_toronto_oct2024.json \
                              out/cmhc_rental_medians_vancouver_oct2024.json \
                              out/cmhc_rental_medians_montreal_oct2024.json \
                              out/Neighbourhood-Medians-Oct2024.json
"""

def guess_city_from_name(path: str) -> str:
    s = pathlib.Path(path).name.lower()
    for city in ["toronto", "vancouver", "montreal", "ottawa", "calgary", "edmonton", "quebec", "winnipeg", "hamilton"]:
        if city in s:
            # normalize display casing
            return {"toronto":"Toronto","vancouver":"Vancouver","montreal":"Montreal",
                    "ottawa":"Ottawa","calgary":"Calgary","edmonton":"Edmonton",
                    "quebec":"Quebec City","winnipeg":"Winnipeg","hamilton":"Hamilton"}[city]
    # fallback: filename stem
    return pathlib.Path(path).stem

def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def main():
    if len(sys.argv) < 5:
        print(USAGE.strip(), file=sys.stderr)
        sys.exit(2)

    *inputs, out_path = sys.argv[1:]
    merged = {
        "version": "CMHC Oct 2024",
        "source": "local-merged",
        "cities": {}  # { "Toronto": <dataset>, ... }
    }

    for p in inputs:
        city = guess_city_from_name(p)
        data = load_json(p)
        merged["cities"][city] = data

    # small sanity metadata: counts if structure is list-like
    meta = {}
    for city, data in merged["cities"].items():
        if isinstance(data, list):
            meta[city] = {"items": len(data)}
        elif isinstance(data, dict):
            meta[city] = {"keys": len(data)}
        else:
            meta[city] = {"type": type(data).__name__}
    merged["meta"] = meta

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    print(f"Wrote {out_path}")
    print(json.dumps({"cities": list(merged["cities"].keys()), "meta": meta}, indent=2))

if __name__ == "__main__":
    main()
