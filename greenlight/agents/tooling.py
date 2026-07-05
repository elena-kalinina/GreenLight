"""OpenAI-format tool schemas + execution for the Kimi agent loop."""
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from greenlight.engine.ledger import ClaimCheck, ComplianceLedger, OpportunityRecommendation
from greenlight.sources import vultr_rag
from greenlight.tools import (
    compute_risk_exposure,
    discover_claim_opportunities,
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
                    "opportunity_id": {"type": "string"},
                    "claim_text": {"type": "string"},
                    "claim_type": {"type": "string"},
                },
                "required": ["claim_text", "claim_type"],
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
                    "opportunity_id": {"type": "string"},
                    "sku": {"type": "string"},
                    "attribute": {"type": "string"},
                },
                "required": ["sku"],
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
            "name": "discover_claim_opportunities",
            "description": "Scan rising ethical demand (Google Trends) and match unclaimed line materials to substantiatable marketing claims the brand is not yet making.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_opportunity_verdict",
            "description": "Record verdict for a discovered claim opportunity after regulation retrieval and supplier cert check.",
            "parameters": {
                "type": "object",
                "properties": {
                    "opportunity_id": {"type": "string"},
                    "status": {"type": "string", "enum": ["substantiated", "needs-evidence", "rejected"]},
                    "citation": {"type": "string"},
                    "regulation": {"type": "string"},
                    "remediation": {"type": "string"},
                },
                "required": ["opportunity_id", "status", "citation"],
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
    discovered: List[dict] = field(default_factory=list)
    discovery_called: bool = False
    finished: bool = False

    def claim_row(self, claim_id: str) -> Optional[dict]:
        for c in self.plan_claims:
            if c["claim_id"] == claim_id:
                return c
        return None

    def opportunity_row(self, opportunity_id: str) -> Optional[dict]:
        for o in self.discovered:
            if o.get("opportunity_id") == opportunity_id:
                return o
        return None


def _trace_key(args: dict) -> str:
    if args.get("claim_id"):
        return args["claim_id"]
    if args.get("opportunity_id"):
        return f"opp:{args['opportunity_id']}"
    return ""


def _trace(ctx: ToolContext, key: str) -> dict:
    if key not in ctx.claim_trace:
        ctx.claim_trace[key] = {}
    return ctx.claim_trace[key]


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
        key = _trace_key(args)
        reg = vultr_rag.search_regulations(args["claim_text"], args.get("claim_type", ""))
        _trace(ctx, key)["regulation"] = reg
        ev.emit(
            "retrieval",
            "ClaimChecker",
            claim_id=args.get("claim_id"),
            opportunity_id=args.get("opportunity_id"),
            retrieval=1,
            text="regulation retrieval #1",
            source=reg.get("source"),
            live=reg.get("live", False),
            citation=reg.get("citation"),
        )
        return reg

    if name == "lookup_supplier_cert":
        key = _trace_key(args)
        cert = vultr_rag.lookup_supplier_cert(args["sku"], args.get("attribute"))
        _trace(ctx, key)["cert"] = cert
        ev.emit(
            "retrieval",
            "ClaimChecker",
            claim_id=args.get("claim_id"),
            opportunity_id=args.get("opportunity_id"),
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

    if name == "discover_claim_opportunities":
        declared = [
            {"sku": c["sku"], "text": c["text"], "meta": c.get("meta") or {}}
            for c in ctx.plan_claims
        ]
        result = discover_claim_opportunities(line, declared)
        ctx.discovery_called = True
        ctx.discovered = result.get("opportunities") or []
        if ctx.discovered:
            ev.emit(
                "agent",
                "Kimi-K2.6",
                text=(
                    f"Found {len(ctx.discovered)} rising-demand claim opportunities the line could add: "
                    + ", ".join(o["opportunity_id"] for o in ctx.discovered)
                ),
            )
        for opp in ctx.discovered:
            ev.emit(
                "opportunity",
                "ClaimDiscovery",
                opportunity_id=opp["opportunity_id"],
                sku=opp["sku"],
                text=opp["claim_text"],
                trend_keyword=opp["trend_keyword"],
                demand_index=opp["demand_index"],
                uplift_pct=opp.get("uplift_pct"),
                status="candidate",
            )
        ev.emit(
            "tool",
            "discover_claim_opportunities",
            text=f"{len(ctx.discovered)} opportunities · rising ethical demand × line materials",
            **result,
        )
        return result

    if name == "submit_opportunity_verdict":
        return _submit_opportunity_verdict(ctx, args)

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

    if row["type"] == "certified_material" and status == "substantiated":
        cert = trace.get("cert")
        if not cert:
            return {"error": "call lookup_supplier_cert before submitting verdict for certified_material claim"}
        tc = cert.get("transaction")
        if not tc or tc.get("status") != "VALID" or tc.get("linkedSku") != row["sku"]:
            status = "needs-evidence"
            args["remediation"] = args.get("remediation") or (
                "No valid Transaction Certificate on file for this named certification scheme."
            )
            citation = citation or "Regulation checked — supplier shipment evidence missing."

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


def _submit_opportunity_verdict(ctx: ToolContext, args: dict) -> dict:
    oid = args["opportunity_id"]
    row = ctx.opportunity_row(oid)
    if not row:
        return {"error": f"unknown opportunity_id {oid} — call discover_claim_opportunities first"}

    status = args["status"]
    citation = (args.get("citation") or "").strip()
    trace = _trace(ctx, f"opp:{oid}")

    if status == "substantiated" and not citation:
        return {"error": "citation required — call search_regulations first"}

    if "regulation" not in trace and status != "rejected":
        return {"error": "call search_regulations with opportunity_id before submitting verdict"}

    cert = trace.get("cert") or {}
    tc = cert.get("transaction")
    if status == "substantiated":
        if not tc or tc.get("status") != "VALID" or tc.get("linkedSku") != row["sku"]:
            status = "needs-evidence"
            args["remediation"] = args.get("remediation") or "No valid Transaction Certificate on file for this shipment."
        elif not cert.get("scope_valid"):
            status = "needs-evidence"
            args["remediation"] = args.get("remediation") or "Scope Certificate missing or expired."

    rec = next((o for o in ctx.ledger.opportunities if o.opportunity_id == oid), None)
    if not rec:
        rec = OpportunityRecommendation(
            opportunity_id=oid,
            sku=row["sku"],
            text=row["claim_text"],
            claim_type=row["claim_type"],
            trend_keyword=row.get("trend_keyword"),
            demand_index=row.get("demand_index"),
            uplift_pct=row.get("uplift_pct"),
            meta=row,
        )
        ctx.ledger.opportunities.append(rec)

    rec.status = status
    rec.citation = citation
    rec.regulation = args.get("regulation")
    rec.remediation = args.get("remediation")

    ctx.events.emit(
        "opportunity",
        "ClaimDiscovery",
        opportunity_id=oid,
        sku=row["sku"],
        text=row["claim_text"],
        trend_keyword=row.get("trend_keyword"),
        demand_index=row.get("demand_index"),
        uplift_pct=row.get("uplift_pct"),
        status=status,
        citation=citation,
        remediation=rec.remediation,
        recommend_add=(status == "substantiated"),
    )
    return {"ok": True, "opportunity_id": oid, "status": status}


def _finalize(ctx: ToolContext, args: dict) -> dict:
    ledger = ctx.ledger

    commercial_missing = [
        tool
        for tool, key in (
            ("forecast_demand", "demand_index"),
            ("market_context", "wtp_premium_pct"),
            ("project_line_margin", "projected_contribution_eur"),
        )
        if not ledger.commercial.get(key)
    ]
    if commercial_missing:
        ctx.events.emit(
            "agent",
            "coordinator",
            text=f"Blocked finalize — commercial analysis incomplete: {', '.join(commercial_missing)}",
        )
        return {
            "error": (
                "Cannot finalize — the commercial upside must be sized first. "
                f"Call these tools before finalize_determination: {', '.join(commercial_missing)}."
            ),
            "pending_tools": commercial_missing,
        }

    adjudicated = {c.claim_id for c in ledger.claims}
    expected = {c["claim_id"] for c in ctx.plan_claims}
    missing = sorted(expected - adjudicated)
    if missing:
        ctx.events.emit(
            "agent",
            "coordinator",
            text=f"Blocked finalize — {len(missing)} claim(s) still need a verdict: {', '.join(missing)}",
        )
        return {
            "error": (
                f"Cannot finalize — {len(missing)} claim(s) still need a verdict: "
                f"{', '.join(missing)}. Call search_regulations, then submit_claim_verdict "
                "for EACH remaining claim before finalize_determination."
            ),
            "pending_claims": missing,
        }

    if not ctx.discovery_called:
        ctx.events.emit(
            "agent",
            "coordinator",
            text="Blocked finalize — call discover_claim_opportunities before finalize_determination",
        )
        return {
            "error": (
                "Cannot finalize — call discover_claim_opportunities after adjudicating claims, "
                "then vet each returned opportunity (search_regulations, lookup_supplier_cert, "
                "submit_opportunity_verdict) before finalize_determination."
            ),
        }

    pending_opps = sorted(
        o["opportunity_id"]
        for o in ctx.discovered
        if o["opportunity_id"] not in {x.opportunity_id for x in ledger.opportunities}
    )
    if pending_opps:
        ctx.events.emit(
            "agent",
            "coordinator",
            text=f"Blocked finalize — {len(pending_opps)} discovered opportunity(ies) still need a verdict: {', '.join(pending_opps)}",
        )
        return {
            "error": (
                f"Cannot finalize — vet discovered opportunities: {', '.join(pending_opps)}. "
                "For each: search_regulations, lookup_supplier_cert, submit_opportunity_verdict."
            ),
            "pending_opportunities": pending_opps,
        }

    blocked = len(ledger.blocked)
    cleared = len(ledger.cleared)
    upside = ledger.commercial.get("projected_contribution_eur", 0)
    demand_idx = ledger.commercial.get("demand_index", 1.0)
    positioning_uplift = round(upside * 0.12 * demand_idx, 0)
    recommended = ledger.recommended_opportunities
    opp_uplift = 0
    for o in recommended:
        pct = (o.uplift_pct or 5) / 100.0
        opp_uplift += round(upside * pct * (o.demand_index or 1.0) / len(ctx.line["skus"]), 0)
    net_upside = round(upside + positioning_uplift + opp_uplift, 0)
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
        "opportunity_uplift_eur": opp_uplift,
        "net_upside_eur": net_upside,
        "recommended_opportunities": [
            {
                "opportunity_id": o.opportunity_id,
                "sku": o.sku,
                "text": o.text,
                "trend_keyword": o.trend_keyword,
                "demand_index": o.demand_index,
                "uplift_pct": o.uplift_pct,
                "citation": o.citation,
            }
            for o in recommended
        ],
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
