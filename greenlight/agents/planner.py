"""Launch planner — decompose line into commercial steps + claims × regulations."""
import json

from greenlight import config


COMMERCIAL_STEPS = [
    "forecast_demand",
    "market_context",
    "project_margin (line rollup)",
]


def load_line():
    return json.loads(config.LINE_PATH.read_text())


def propose_plan(events):
    line = load_line()
    claims = []
    for sku in line["skus"]:
        for mc in sku.get("marketing_claims", []):
            claims.append({
                "claim_id": mc["id"],
                "sku": sku["sku"],
                "text": mc["text"],
                "type": mc["type"],
                "attribute": mc.get("attribute"),
                "meta": mc,
            })
    events.emit(
        "plan",
        "LaunchPlanner",
        text=f"AW26 line: {len(line['skus'])} SKUs, {len(claims)} marketing claims",
        commercial_steps=COMMERCIAL_STEPS,
        claims=[c["claim_id"] for c in claims],
    )
    return line, claims
