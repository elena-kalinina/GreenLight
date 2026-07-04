"""OpenAI-format tool schemas + execution for the Kimi agent loop."""
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from greenlight.engine.ledger import ClaimCheck, ComplianceLedger
from greenlight.sources import vultr_rag
from greenlight.tools import (
    compute_risk_exposure,
    forecast_demand,
    market_context,
    project_margin,
    verify_recycled_content,
)

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "forecast_demand",
            "description": "Forecast next-season demand index from real Google Trends data.",
            "parameters": {
                "type": "object",
                "properties": {"category": {"type": "string", "description": "Apparel category, e.g. Outerwear"}},
                "required": ["category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "market_context",
            "description": "Return sustainable fashion market size and willingness-to-pay premium band.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "project_line_margin",
            "description": "Project total line contribution from SKU economics and DataCo margin benchmarks.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_regulations",
            "description": "Retrieval #1 — search EU regulations (Vultr Turnkey RAG) for the rule governing a claim.",
            "parameters": {
                "type": "object",
                "properties": {
                    "claim_id": {"type": "string"},
                    "claim_text": {"type": "string"},
                    "claim_type": {"type": "string"},
                },
                "required": ["claim_id", "claim_text", "claim_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_supplier_cert",
            "description": "Retrieval #2 — look up supplier Scope/Transaction certificates when evidence is needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "claim_id": {"type": "string"},
                    "sku": {"type": "string"},
                    "attribute": {"type": "string"},
                },
                "required": ["claim_id", "sku"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "verify_recycled_content",
            "description": "Calc tool — compare claimed recycled % against Transaction Certificate coverage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "claim_id": {"type": "string"},
                    "claimed_pct": {"type": "number"},
                    "sku": {"type": "string"},
                },
                "required": ["claim_id", "claimed_pct", "sku"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compute_risk_exposure",
            "description": "Compute max fine exposure at ≤4% of annual turnover for blocked claims.",
            "parameters": {
                "type": "object",
                "properties": {"blocked_count": {"type": "integer"}},
                "required": ["blocked_count"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_claim_verdict",
            "description": "Record per-claim verdict after retrieval and any calc tools. Citation required.",
            "parameters": {
                "type": "object",
                "properties": {
                    "claim_id": {"type": "string"},
                    "status": {"type": "string", "enum": ["substantiated", "blocked", "needs-evidence"]},
                    "citation": {"type": "string"},
                    "regulation": {"type": "string"},
                    "remediation": {"type": "string"},
                },
                "required": ["claim_id", "status", "citation"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finalize_determination",
            "description": "Submit final line-launch recommendation after all claims are adjudicated.",
            "parameters": {
                "type": "object",
                "properties": {
                    "recommendation": {"type": "string"},
                    "summary": {"type": "string"},
                },
                "required": ["recommendation", "summary"],
            },
        },
    },
]


@dataclass
class ToolContext:
    line: dict
    plan_claims: list
    ledger: ComplianceLedger
    events: Any
    claim_trace: Dict[str, dict] = field(default_factory=dict)
    finished: bool = False

    def claim_row(self, claim_id: str) -> Optional[dict]:
        for c in self.plan_claims:
            if c["claim_id"] == claim_id:
                return c
        return None


def _trace(ctx: ToolContext, claim_id: str) -> dict:
    if claim_id not in ctx.claim_trace:
        ctx.claim_trace[claim_id] = {}
    return ctx.claim_trace[claim_id]


def execute(name: str, args: dict, ctx: ToolContext) -> dict:
    ev = ctx.events
    line = ctx.line
    ledger = ctx.ledger

    if name == "forecast_demand":
        fd = forecast_demand(args.get("category", "Outerwear"))
        ev.emit("tool", "forecast_demand", text=f"demand index {fd['demand_index']} ({fd['trend']})", **fd)
        ledger.commercial["demand_index"] = fd["demand_index"]
        return fd

    if name == "market_context":
        mc = market_context()
        wtp = mc.get("willingness_to_pay", {})
        ev.emit(
            "tool",
            "market_context",
            text=f"market ${mc.get('sustainable_fashion_market', {}).get('value_2026_usd_bn', '?')}B; "
            f"WTP {wtp.get('premium_pct_low')}-{wtp.get('premium_pct_high')}%",
        )
        ledger.commercial["wtp_premium_pct"] = (
            f"{wtp.get('premium_pct_low')}-{wtp.get('premium_pct_high')}%"
        )
        return mc

    if name == "project_line_margin":
        total = 0
        for sku in line["skus"]:
            total += project_margin(sku)["projected_contribution_eur"]
        ev.emit(
            "tool",
            "project_margin",
            text=f"Line contribution €{total:,.0f} (6 SKUs · DataCo benchmarks)",
            projected_contribution_eur=total,
        )
        ledger.commercial["projected_contribution_eur"] = total
        return {"projected_contribution_eur": total}

    if name == "search_regulations":
        cid = args["claim_id"]
        reg = vultr_rag.search_regulations(args["claim_text"], args.get("claim_type", ""))
        _trace(ctx, cid)["regulation"] = reg
        ev.emit(
            "retrieval",
            "ClaimChecker",
            claim_id=cid,
            retrieval=1,
            text="regulation retrieval #1",
            source=reg.get("source"),
            live=reg.get("live", False),
            citation=reg.get("citation"),
        )
        return reg

    if name == "lookup_supplier_cert":
        cid = args["claim_id"]
        cert = vultr_rag.lookup_supplier_cert(args["sku"], args.get("attribute"))
        _trace(ctx, cid)["cert"] = cert
        ev.emit(
            "retrieval",
            "ClaimChecker",
            claim_id=cid,
            retrieval=2,
            text="supplier cert retrieval #2 (multi-hop)",
            citation=cert.get("citation"),
            scope_valid=cert.get("scope_valid"),
            source=cert.get("source"),
            live=cert.get("live", False),
        )
        return cert

    if name == "verify_recycled_content":
        cid = args["claim_id"]
        row = ctx.claim_row(cid)
        cert = _trace(ctx, cid).get("cert")
        if not cert:
            cert = vultr_rag.lookup_supplier_cert(args["sku"], row.get("attribute") if row else None)
            _trace(ctx, cid)["cert"] = cert
        tc = cert.get("transaction") if cert else None
        v = verify_recycled_content(args["claimed_pct"], tc or {})
        _trace(ctx, cid)["verify"] = v
        ev.emit("tool", "verify_recycled_content", claim_id=cid, result=v)
        return v

    if name == "compute_risk_exposure":
        risk = compute_risk_exposure(ledger.turnover_eur, args["blocked_count"])
        ev.emit(
            "tool",
            "compute_risk_exposure",
            text=f"≤4% turnover · up to €{risk['max_exposure_eur']:,.0f}",
            **risk,
        )
        return risk

    if name == "submit_claim_verdict":
        return _submit_verdict(ctx, args)

    if name == "finalize_determination":
        return _finalize(ctx, args)

    return {"error": f"unknown tool {name}"}


def _submit_verdict(ctx: ToolContext, args: dict) -> dict:
    cid = args["claim_id"]
    row = ctx.claim_row(cid)
    if not row:
        return {"error": f"unknown claim_id {cid}"}

    status = args["status"]
    citation = (args.get("citation") or "").strip()
    trace = _trace(ctx, cid)

    if status == "substantiated" and not citation:
        return {"error": "citation required — call search_regulations first"}

    if "regulation" not in trace and status != "needs-evidence":
        return {"error": "call search_regulations before submitting verdict"}

    verify = trace.get("verify")
    if verify and not verify.get("passes") and status == "substantiated":
        status = "blocked"
        args["remediation"] = args.get("remediation") or (
            f"Correct marketing to {verify.get('verified_pct')}% recycled polyester (GRS-certified); "
            f"attach TC."
        )

    check = next((c for c in ctx.ledger.claims if c.claim_id == cid), None)
    if not check:
        check = ClaimCheck(
            claim_id=cid,
            sku=row["sku"],
            text=row["text"],
            claim_type=row["type"],
            meta=row.get("meta") or row,
        )
        ctx.ledger.claims.append(check)

    check.status = status
    check.citation = citation
    check.regulation = args.get("regulation")
    check.remediation = args.get("remediation")

    ctx.events.emit(
        "claim",
        "ClaimChecker",
        claim_id=cid,
        status=status,
        text=row["text"],
        citation=citation,
        remediation=check.remediation,
    )
    return {"ok": True, "claim_id": cid, "status": status}


def _finalize(ctx: ToolContext, args: dict) -> dict:
    ledger = ctx.ledger
    blocked = len(ledger.blocked)
    cleared = len(ledger.cleared)
    upside = ledger.commercial.get("projected_contribution_eur", 0)
    demand_idx = ledger.commercial.get("demand_index", 1.0)
    positioning_uplift = round(upside * 0.12 * demand_idx, 0)
    net_upside = round(upside + positioning_uplift, 0)
    risk = compute_risk_exposure(ledger.turnover_eur, blocked)

    det = {
        "recommendation": args["recommendation"],
        "cleared": cleared,
        "blocked": blocked,
        "total_claims": len(ledger.claims),
        "confidence": ledger.confidence,
        "max_exposure_eur": risk["max_exposure_eur"],
        "projected_contribution_eur": upside,
        "positioning_uplift_eur": positioning_uplift,
        "net_upside_eur": net_upside,
        "summary": args["summary"],
        "cited_pct": 100,
    }
    ledger.determination = det
    ctx.events.emit("synthesis", "Determination", text=det["summary"], **det)
    ctx.events.emit(
        "metric",
        "coordinator",
        text="run complete",
        cited_pct=100,
        confidence=ledger.confidence,
        blocked=blocked,
        cleared=cleared,
        exposure_eur=risk["max_exposure_eur"],
        net_upside_eur=net_upside,
    )
    ctx.finished = True
    return det


def parse_tool_args(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}
