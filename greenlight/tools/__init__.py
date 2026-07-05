"""Commercial + compliance tools (stubbed for Block A; real logic in Block B/C)."""
import csv
import json
from pathlib import Path

from greenlight import config


def forecast_demand(category="Outerwear"):
    path = config.DATA / "demand" / "trends_sustainability.csv"
    if not path.exists():
        return {"demand_index": 1.0, "trend": "stable", "source": "stub"}
    rows = list(csv.DictReader(open(path)))
    col = "sustainable fashion"
    if not rows or col not in rows[0]:
        return {"demand_index": 1.0, "trend": "stable", "source": "stub"}
    recent = [float(r[col]) for r in rows[-12:] if r.get(col)]
    prior = [float(r[col]) for r in rows[-24:-12] if r.get(col)]
    avg_r = sum(recent) / len(recent) if recent else 1
    avg_p = sum(prior) / len(prior) if prior else avg_r
    idx = round(avg_r / avg_p, 2) if avg_p else 1.0
    return {
        "demand_index": idx,
        "trend": "rising" if idx > 1.05 else "stable",
        "category": category,
        "source": "Google Trends (real)",
        "keywords": ["sustainable fashion", "recycled polyester", "organic cotton"],
    }


def market_context():
    p = config.DATA / "market" / "market_context.json"
    return json.loads(p.read_text()) if p.exists() else {}


def project_margin(sku_row):
    bench = config.DATA / "margins" / "datac_apparel_benchmarks.csv"
    ratio = 0.12
    if bench.exists():
        for row in csv.DictReader(open(bench)):
            if row.get("category", "").lower() in sku_row.get("category", "").lower():
                ratio = float(row["avg_profit_ratio"])
                break
    retail = sku_row.get("retail_price_eur", 0)
    cost = sku_row.get("unit_cost_eur", 0)
    units = sku_row.get("planned_units", 0)
    margin_per = retail - cost
    return {
        "sku": sku_row.get("sku"),
        "unit_margin_eur": round(margin_per, 2),
        "benchmark_profit_ratio": ratio,
        "projected_contribution_eur": round(margin_per * units, 0),
        "source": "line economics + DataCo benchmark",
    }


def verify_recycled_content(claimed_pct, tc_payload):
    """Recompute claimed % vs TC — the calc tool for the wow."""
    import json as _json
    if isinstance(tc_payload, str):
        try:
            tc_payload = _json.loads(tc_payload)
        except _json.JSONDecodeError:
            return {"verified_pct": None, "passes": False}
    covered = None
    if isinstance(tc_payload, dict):
        prods = tc_payload.get("products") or []
        if prods:
            covered = prods[0].get("certifiedRecycledContentPct")
    if covered is None:
        return {"verified_pct": None, "passes": False}
    return {
        "claimed_pct": claimed_pct,
        "verified_pct": covered,
        "passes": covered >= claimed_pct,
        "gap": claimed_pct - covered if claimed_pct > covered else 0,
    }


def _trend_index(path, column):
    if not path.exists():
        return {"demand_index": 1.0, "trend": "stable", "source": "stub"}
    rows = list(csv.DictReader(open(path)))
    if not rows or column not in rows[0]:
        return {"demand_index": 1.0, "trend": "stable", "source": "stub"}
    recent = [float(r[column]) for r in rows[-12:] if r.get(column)]
    prior = [float(r[column]) for r in rows[-24:-12] if r.get(column)]
    avg_r = sum(recent) / len(recent) if recent else 1
    avg_p = sum(prior) / len(prior) if prior else avg_r
    idx = round(avg_r / avg_p, 2) if avg_p else 1.0
    return {
        "demand_index": idx,
        "trend": "rising" if idx > 1.05 else "stable",
        "source": "Google Trends (real)",
    }


def discover_claim_opportunities(line, declared_claims):
    """Scan ethical demand trends and match unclaimed line materials to substantiatable claims."""
    mapping_path = config.DATA / "demand" / "claim_opportunities.json"
    trends_path = config.DATA / "demand" / "trends_ethical.csv"
    if not mapping_path.exists():
        return {"opportunities": [], "source": "none"}
    mappings = json.loads(mapping_path.read_text()).get("mappings", [])
    declared_attrs = set()
    declared_skus_claimed = set()
    for c in declared_claims or []:
        meta = c.get("meta") or c
        if meta.get("attribute"):
            declared_attrs.add(meta["attribute"])
        if c.get("text"):
            declared_skus_claimed.add((c.get("sku"), c.get("text", "").lower()))

    sku_by_id = {s["sku"]: s for s in line.get("skus", [])}
    out = []
    for m in mappings:
        sku_row = sku_by_id.get(m["sku"])
        if not sku_row:
            continue
        attrs = set(sku_row.get("attributes") or [])
        if m["material_attribute"] not in attrs:
            continue
        if m["material_attribute"] in declared_attrs:
            continue
        if (m["sku"], m["claim_text"].lower()) in declared_skus_claimed:
            continue
        trend = _trend_index(trends_path, m["trend_column"])
        if trend["demand_index"] < 1.02:
            continue
        out.append({
            "opportunity_id": m["opportunity_id"],
            "sku": m["sku"],
            "sku_name": sku_row.get("name"),
            "claim_text": m["claim_text"],
            "claim_type": m["claim_type"],
            "scheme": m.get("scheme"),
            "evidence_attribute": m["evidence_attribute"],
            "trend_keyword": m["trend_keyword"],
            "demand_index": trend["demand_index"],
            "trend": trend["trend"],
            "uplift_pct": m.get("uplift_pct", 5),
            "source": trend["source"],
        })
    return {"opportunities": out, "count": len(out), "source": "Google Trends + line attributes"}


def compute_risk_exposure(turnover_eur, blocked_count):
    cap = round(turnover_eur * 0.04, 0)
    return {
        "max_exposure_eur": cap,
        "blocked_claims": blocked_count,
        "basis": "UCPD/Omnibus ≤4% turnover for widespread infringement",
    }
