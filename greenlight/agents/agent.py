"""Kimi-K2.6 agent loop — plans, calls tools, decides, grounds in documents."""
import json

from greenlight import config, llm
from greenlight.agents.tooling import TOOL_SCHEMAS, ToolContext, execute, parse_tool_args
from greenlight.engine import policy
from greenlight.engine.ledger import ComplianceLedger

MAX_TURNS = 48

SYSTEM = """You are GreenLight, an enterprise agent for a fashion retail compliance desk.

Your job: decide whether to green-light the AW26 line for launch by weighing commercial upside
against regulatory and evidence risk under Directive (EU) 2024/825 (ECGT).

WORKFLOW — follow in order:
1. FIRST call forecast_demand, market_context, project_line_margin (required before claim checks).
2. For EACH of the 6 marketing claims (C1–C6):
   a. Call search_regulations (retrieval #1) before any verdict.
   b. If recycled_content and evidence is needed: lookup_supplier_cert (retrieval #2), then verify_recycled_content.
   c. Call submit_claim_verdict with status, citation, and remediation if blocked.
3. Call discover_claim_opportunities — scan rising ethical demand for claims the line could add but is not yet making.
   For EACH returned opportunity (e.g. O1, O2):
   a. Call search_regulations with opportunity_id (not claim_id).
   b. Call lookup_supplier_cert with opportunity_id, sku, and evidence_attribute.
   c. Call submit_opportunity_verdict — recommend ADD TO LAUNCH only if substantiated with valid cert.
4. Call compute_risk_exposure with the number of blocked claims.
5. Call finalize_determination with recommendation and summary (include recommended claim additions).

RULES:
- You MUST submit_claim_verdict for ALL 6 claims (C1–C6) before discovery.
- You MUST call discover_claim_opportunities and vet every returned opportunity before finalize.
- Generic environmental claims ("eco-friendly", "green", "sustainable") → BLOCKED under ECGT Annex I 4a.
- Recycled % claims: if verify_recycled_content.passes is false, BLOCK and cite the TC gap.
- Named certification schemes (GOTS, OEKO-TEX, RDS, RWS) with valid supplier cert → substantiated.
- Discovered opportunities: only recommend if RDS/RWS (or other named scheme) TC substantiates the shipment.
- Recommendation: GREEN-LIGHT WITH CONDITIONS if any claims blocked, else GREEN-LIGHT.
- In finalize summary, mention any substantiated opportunities as recommended additions to launch marketing.

ACCOUNTABILITY:
- On your FIRST response, write 2–4 sentences outlining your plan (commercial sizing → claim checks → discovery → risk → determination) BEFORE calling any tools.
- When starting a new workflow phase, you may add one brief sentence explaining what you are doing next.
"""

PLAN_STEPS = [
    {"id": "commercial", "label": "Size commercial upside", "detail": "forecast_demand · market_context · project_line_margin"},
    {"id": "claims", "label": "Adjudicate 6 marketing claims", "detail": "regulation retrieval · supplier certs · per-claim verdicts (C1–C6)"},
    {"id": "discovery", "label": "Discover claim opportunities", "detail": "ethical demand scan · vet RDS/RWS claims · recommend additions"},
    {"id": "risk", "label": "Quantify risk exposure", "detail": "compute_risk_exposure (≤4% turnover cap)"},
    {"id": "finalize", "label": "File launch determination", "detail": "recommendation · summary · recommended additions"},
]

_TOOL_STAGE = {
    "forecast_demand": "commercial",
    "market_context": "commercial",
    "project_line_margin": "commercial",
    "search_regulations": "claims",
    "lookup_supplier_cert": "claims",
    "verify_recycled_content": "claims",
    "submit_claim_verdict": "claims",
    "discover_claim_opportunities": "discovery",
    "submit_opportunity_verdict": "discovery",
    "compute_risk_exposure": "risk",
    "finalize_determination": "finalize",
}


def _stage_label(stage_id: str) -> str:
    for step in PLAN_STEPS:
        if step["id"] == stage_id:
            return step["label"]
    return stage_id


def _tool_stage(name: str, args: dict):
    if name in ("search_regulations", "lookup_supplier_cert") and args.get("opportunity_id"):
        return "discovery"
    return _TOOL_STAGE.get(name)


def run(line, plan_claims, events, human):
    """Agent-driven line review. Returns ComplianceLedger."""
    ev = events
    ev.emit("task", "coordinator", text=f"Review {line['brand']} {line['season']} line for launch")

    gate, why = policy.decide("gate_line")
    ev.emit("escalation", "coordinator", text=f"ASK human: gate line review? ({why})")
    reply = human.ask("Approve GreenLight review of this line?", options=["approve"])
    ev.emit("human_reply", "human", text=reply)

    ledger = ComplianceLedger(
        brand=line["brand"],
        season=line["season"],
        turnover_eur=line["annual_turnover_eur"],
    )
    ctx = ToolContext(line=line, plan_claims=plan_claims, ledger=ledger, events=ev)

    claims_brief = [
        {
            "claim_id": c["claim_id"],
            "sku": c["sku"],
            "text": c["text"],
            "type": c["type"],
            "claimed_recycled_pct": c.get("meta", {}).get("claimed_recycled_pct"),
        }
        for c in plan_claims
    ]

    line_attrs = [
        {"sku": s["sku"], "name": s["name"], "attributes": s.get("attributes", []), "composition": s.get("composition")}
        for s in line["skus"]
    ]

    user_msg = (
        f"Review line for {line['brand']} {line['season']}. "
        f"Annual turnover €{line['annual_turnover_eur']:,.0f}. "
        f"Marketing claims:\n{json.dumps(claims_brief, indent=2)}\n\n"
        f"Line materials (for discovery — some ethical claims may be possible but not yet declared):\n"
        f"{json.dumps(line_attrs, indent=2)}\n\n"
        "Use tools for every step. Adjudicate all 6 claims, discover rising-demand opportunities, "
        "vet each opportunity, then finalize."
    )
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user_msg},
    ]

    ev.emit("agent_plan", "Kimi-K2.6", steps=PLAN_STEPS)
    current_stage = None

    for turn in range(MAX_TURNS):
        msg = llm.chat(messages, model=config.MODEL_BRAIN, max_tokens=1024, tools=TOOL_SCHEMAS)
        if msg.get("content"):
            ev.emit("agent", "Kimi-K2.6", text=msg["content"][:600])

        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            if ctx.finished:
                break
            messages.append(msg)
            messages.append({
                "role": "user",
                "content": "Continue — use tools to adjudicate remaining claims, discover opportunities, and finalize_determination.",
            })
            continue

        messages.append(msg)
        for tc in tool_calls:
            fn = tc.get("function") or {}
            name = fn.get("name", "")
            args = parse_tool_args(fn.get("arguments"))
            stage_id = _tool_stage(name, args)
            if stage_id and stage_id != current_stage:
                current_stage = stage_id
                ev.emit(
                    "agent_stage",
                    "Kimi-K2.6",
                    stage_id=stage_id,
                    label=_stage_label(stage_id),
                    tool=name,
                    status="active",
                )
            ev.emit("tool_call", "Kimi-K2.6", tool=name, args=args, agent_turn=turn + 1, stage_id=stage_id)
            result = execute(name, args, ctx)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id", name),
                "content": json.dumps(result, default=str)[:4000],
            })
            if ctx.finished:
                if current_stage:
                    ev.emit("agent_stage", "Kimi-K2.6", stage_id=current_stage, label=_stage_label(current_stage), status="done")
                break
        if ctx.finished:
            break

    if not ledger.determination:
        from greenlight.agents import determination

        _backfill_commercial(ctx)
        determination.synthesize(ledger, ev)
    elif not ledger.commercial.get("projected_contribution_eur"):
        _backfill_commercial(ctx)

    gate2, why2 = policy.decide("publish_determination", blocked_claims=len(ledger.blocked))
    if gate2 != policy.PROCEED:
        ev.emit("escalation", "coordinator", text=f"{gate2.upper()}: file determination? ({why2})")
        reply2 = human.ask("File the launch determination?", options=["approve"])
        ev.emit("human_reply", "human", text=reply2)

    rec = ledger.determination["recommendation"] if ledger.determination else "done"
    ev.emit("decision", "coordinator", text=rec)
    return ledger


def _backfill_commercial(ctx: ToolContext):
    """Ensure commercial metrics exist if the agent skipped those tool calls."""
    ledger = ctx.ledger
    if ledger.commercial.get("projected_contribution_eur"):
        return
    execute("forecast_demand", {"category": "Outerwear"}, ctx)
    execute("market_context", {}, ctx)
    execute("project_line_margin", {}, ctx)


def run_or_fallback(line, plan_claims, events, human):
    """Run Kimi agent when enabled; fall back to deterministic pipeline on failure."""
    if not config.use_agent():
        return None
    try:
        return run(line, plan_claims, events, human)
    except Exception as exc:
        events.emit("error", "Agent", text=f"Agent loop failed ({exc}) — deterministic fallback")
        return None
