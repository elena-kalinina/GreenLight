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
3. Call compute_risk_exposure with the number of blocked claims.
4. Call finalize_determination with recommendation and summary.

RULES:
- Generic environmental claims ("eco-friendly", "green", "sustainable") → BLOCKED under ECGT Annex I 4a.
- Recycled % claims: if verify_recycled_content.passes is false, BLOCK and cite the TC gap.
- Named certification schemes (GOTS, OEKO-TEX) with valid supplier cert → substantiated.
- Recommendation: GREEN-LIGHT WITH CONDITIONS if any claims blocked, else GREEN-LIGHT.
"""


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

    user_msg = (
        f"Review line for {line['brand']} {line['season']}. "
        f"Annual turnover €{line['annual_turnover_eur']:,.0f}. "
        f"Marketing claims:\n{json.dumps(claims_brief, indent=2)}\n\n"
        "Use tools for every step. Adjudicate all 6 claims, then finalize."
    )
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user_msg},
    ]

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
                "content": "Continue — use tools to adjudicate remaining claims and finalize_determination.",
            })
            continue

        messages.append(msg)
        for tc in tool_calls:
            fn = tc.get("function") or {}
            name = fn.get("name", "")
            args = parse_tool_args(fn.get("arguments"))
            result = execute(name, args, ctx)
            ev.emit("tool_call", "Kimi-K2.6", tool=name, args=args, agent_turn=turn + 1)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id", name),
                "content": json.dumps(result, default=str)[:4000],
            })
            if ctx.finished:
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
    ctx.events.emit("agent", "coordinator", text="Backfilling commercial tools the agent skipped")
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
