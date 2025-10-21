# tests/tests_tools.py
import json

from lambdas.evaluate_rent_affordability import lambda_handler as afford
from lambdas.get_neighbourhood_stats import lambda_handler as get_stats
from lambdas.get_rent_data import lambda_handler as get_rent
from lambdas.suggest_neighbourhoods import lambda_handler as suggest


def pretty(name, resp):
    try:
        body = json.loads(resp["body"]) if isinstance(resp.get("body"), str) else resp.get("body", {})
    except Exception:
        body = resp.get("body")
    print(f"\n=== {name} ===")
    print("status:", resp.get("statusCode"))
    print("keys:", list(body.keys()) if isinstance(body, dict) else type(body))

def main():
    r = get_rent({"city":"Toronto","property_type":"1bed","include_neighbourhoods":False}, None)
    pretty("get_rent_data", r)

    s = get_stats({"city":"Toronto","property_type":"1bed"}, None)
    pretty("get_neighbourhood_stats", s)

    sg = suggest({
        "city":"Toronto","property_type":"1bed",
        "income_annual":80000,
        "prefs":{"max_distance_km":12,"min_transit":60,"target_rent_to_income":0.30},
        "budget_cap":2200
    }, None)
    pretty("suggest_neighbourhoods", sg)

    af = afford({"listing_price":2000,"city_median":1900,"income_annual":72000,"target_ratio":0.30}, None)
    pretty("evaluate_rent_affordability", af)

if __name__ == "__main__":
    main()
