# policy.py — Day 3 minimal router (local only)
# Requires: export PYTHONPATH=.
import json
from typing import Any, Dict, Tuple

from lambdas.evaluate_rent_affordability import lambda_handler as tool_afford
from lambdas.get_neighbourhood_stats import lambda_handler as tool_stats
from lambdas.get_rent_data import lambda_handler as tool_rent
from lambdas.suggest_neighbourhoods import lambda_handler as tool_suggest

SAFE_DEFAULTS = {
    "property_type": "1bed",
    "target_ratio": 0.30,
}

def _resp(plan: str, actions: list, verify: Dict[str, Any], answer: Dict[str, Any]):
    return {"plan": plan, "actions": actions, "verify": verify, "answer": answer}

def classify_intent(user_text: str) -> str:
    t = (user_text or "").lower()
    if any(k in t for k in ["what is rti", "what is rent-to-income", "explain transit score", "what is eps"]):
        return "explain"
    if "afford" in t or "rti" in t or "rent to income" in t:
        return "affordability"
    if any(k in t for k in ["suggest", "recommend", "neighbourhood", "where should i live"]):
        return "suggest"
    if any(k in t for k in ["median", "rent in", "city median"]):
        return "city_rent"
    if "transit" in t:
        return "neigh_stats"
    return "city_rent"

def fill_defaults(args: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(args or {})
    out.setdefault("property_type", SAFE_DEFAULTS["property_type"])
    return out

def maybe_need_city(intent: str) -> bool:
    return intent in {"city_rent", "neigh_stats", "suggest"}

def call(tool, args) -> Tuple[int, Dict[str, Any]]:
    r = tool(args, None)
    body = r.get("body")
    try:
        body = json.loads(body) if isinstance(body, str) else (body or {})
    except Exception:
        body = {"raw": body}
    return r.get("statusCode", 500), body

def decide_and_act(user_text: str, args: Dict[str, Any]) -> Dict[str, Any]:
    intent = classify_intent(user_text)
    args = fill_defaults(args)

    # Ask for city if required and missing
    if maybe_need_city(intent) and not args.get("city"):
        plan = f"Ask user for city for intent={intent}"
        return _resp(plan, [], {"ok": False, "notes": "missing_city"}, {
            "message": "Which city should I check? (Toronto, Montreal, Vancouver)"
        })

    if intent == "explain":
        plan = "No tool; provide definition using policy guidance"
        msg = "Rent-to-income (RTI) is monthly rent divided by monthly income. A common target is ~30%."
        return _resp(plan, [], {"ok": True, "notes": "think_only"}, {"message": msg})

    if intent == "city_rent":
        plan = "Fetch city median via get_rent_data"
        status, body = call(tool_rent, {
            "city": args["city"],
            "property_type": args["property_type"],
            "include_neighbourhoods": False
        })
        actions = [{"tool": "get_rent_data", "args": {"city": args["city"], "property_type": args["property_type"]}, "status": status}]
        if status != 200:
            return _resp(plan, actions, {"ok": False, "notes": body}, {"error": "tool_failed", "details": body})
        return _resp(plan, actions, {"ok": True}, {
            "summary": f'{args["city"]} {args["property_type"]} median = {body.get("median")} {body.get("currency")}',
            "data": body
        })

    if intent == "neigh_stats":
        plan = "Fetch neighbourhood-level transit/medians via get_neighbourhood_stats"
        status, body = call(tool_stats, {
            "city": args["city"],
            "property_type": args["property_type"]
        })
        actions = [{"tool": "get_neighbourhood_stats", "args": {"city": args["city"], "property_type": args["property_type"]}, "status": status}]
        if status != 200:
            return _resp(plan, actions, {"ok": False, "notes": body}, {"error": "tool_failed", "details": body})
        return _resp(plan, actions, {"ok": True}, {
            "summary": f'Found {len(body.get("neighbourhoods", []))} neighbourhoods for {args["city"]}.',
            "data": body
        })

    if intent == "affordability":
        plan = "If city_median missing, fetch via get_rent_data; then compute via evaluate_rent_affordability"
        # Ensure city_median
        city_median = args.get("city_median")
        act = []
        if not city_median and args.get("city"):
            s1, b1 = call(tool_rent, {"city": args["city"], "property_type": args["property_type"], "include_neighbourhoods": False})
            act.append({"tool": "get_rent_data", "status": s1})
            if s1 != 200:
                return _resp(plan, act, {"ok": False, "notes": b1}, {"error": "failed_to_get_city_median", "details": b1})
            city_median = b1.get("median")
        if not all([args.get("listing_price"), city_median, args.get("income_annual")]):
            return _resp(plan, act, {"ok": False, "notes": "missing inputs"}, {
                "message": "Need listing_price, income_annual, and city (or city_median)."
            })
        s2, b2 = call(tool_afford, {
            "listing_price": args["listing_price"],
            "city_median": city_median,
            "income_annual": args["income_annual"],
            "target_ratio": args.get("target_ratio", 0.30)
        })
        act.append({"tool": "evaluate_rent_affordability", "status": s2})
        if s2 != 200:
            return _resp(plan, act, {"ok": False, "notes": b2}, {"error": "afford_failed", "details": b2})
        return _resp(plan, act, {"ok": True}, {"summary": b2.get("verdict"), "metrics": b2})

    if intent == "suggest":
        plan = "Call suggest_neighbourhoods with income/prefs; explain filters"
        s, b = call(tool_suggest, {
            "city": args["city"],
            "property_type": args.get("property_type", "1bed"),
            "income_annual": args.get("income_annual", 80000),
            "prefs": args.get("prefs", {}),
            "budget_cap": args.get("budget_cap"),
            "listing_price": args.get("listing_price")
        })
        actions = [{"tool": "suggest_neighbourhoods", "status": s}]
        if s != 200:
            return _resp(plan, actions, {"ok": False, "notes": b}, {"error": "suggest_failed", "details": b})
        recs = b.get("recommendations", [])
        return _resp(plan, actions, {"ok": True}, {
            "summary": f"Top {len(recs)} neighbourhoods",
            "recommendations": recs,
            "meta": {"city": args["city"], "property_type": args["property_type"]}
        })

    # Fallback
    return _resp("Defaulted to city_rent", [], {"ok": False}, {"message": "Please rephrase or provide a city."})

if __name__ == "__main__":
    # quick demos
    print(json.dumps(decide_and_act("what is rti?", {}), indent=2))
    print(json.dumps(decide_and_act("median rent in Toronto", {"city":"Toronto"}), indent=2))
    print(json.dumps(decide_and_act("check transit", {"city":"Toronto"}), indent=2))
    print(json.dumps(decide_and_act("is this affordable?", {"city":"Toronto","listing_price":2200,"income_annual":80000}), indent=2))
    print(json.dumps(decide_and_act("suggest areas", {"city":"Toronto","income_annual":80000,"prefs":{"min_transit":70}}), indent=2))
