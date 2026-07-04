"""Coordinator — plan → commercial tools → per-claim checks → determination."""
from greenlight.agents import claim_checker, determination, planner
from greenlight.engine import policy
from greenlight.engine.ledger import ClaimCheck, ComplianceLedger
from greenlight.tools import forecast_demand, market_context, project_margin


class Coordinator:
    def __init__(self, events, human):
        self.events = events
        self.human = human

    def run(self):
        ev = self.events
        line, plan_claims = planner.propose_plan(ev)

        ev.emit("task", "coordinator",
                text=f"Review {line['brand']} {line['season']} line for launch")

        gate, why = policy.decide("gate_line")
        ev.emit("escalation", "coordinator", text=f"ASK human: gate line review? ({why})")
        reply = self.human.ask("Approve GreenLight review of this line?", options=["approve"])
        ev.emit("human_reply", "human", text=reply)

        ledger = ComplianceLedger(
            brand=line["brand"],
            season=line["season"],
            turnover_eur=line["annual_turnover_eur"],
        )

        # Commercial layer (real data, deterministic)
        fd = forecast_demand("Outerwear")
        ev.emit("tool", "forecast_demand", text=f"demand index {fd['demand_index']} ({fd['trend']})", **fd)
        mc = market_context()
        wtp = mc.get("willingness_to_pay", {})
        ev.emit("tool", "market_context",
                text=f"market ${mc.get('sustainable_fashion_market', {}).get('value_2026_usd_bn', '?')}B; WTP {wtp.get('premium_pct_low')}-{wtp.get('premium_pct_high')}%")
        total_contrib = 0
        for sku in line["skus"]:
            total_contrib += project_margin(sku)["projected_contribution_eur"]
        ev.emit(
            "tool",
            "project_margin",
            text=f"Line contribution €{total_contrib:,.0f} (6 SKUs · DataCo benchmarks)",
            projected_contribution_eur=total_contrib,
            sku="LINE",
        )
        ledger.commercial = {
            "demand_index": fd["demand_index"],
            "wtp_premium_pct": f"{wtp.get('premium_pct_low')}-{wtp.get('premium_pct_high')}%",
            "projected_contribution_eur": total_contrib,
        }

        for pc in plan_claims:
            check = ClaimCheck(
                claim_id=pc["claim_id"],
                sku=pc["sku"],
                text=pc["text"],
                claim_type=pc["type"],
                meta=pc["meta"],
            )
            claim_checker.check_claim(check, ev)
            ledger.claims.append(check)

        determination.synthesize(ledger, ev)

        gate2, why2 = policy.decide("publish_determination", blocked_claims=len(ledger.blocked))
        if gate2 != policy.PROCEED:
            ev.emit("escalation", "coordinator", text=f"{gate2.upper()}: file determination? ({why2})")
            reply2 = self.human.ask("File the launch determination?", options=["approve"])
            ev.emit("human_reply", "human", text=reply2)

        ev.emit("decision", "coordinator", text=ledger.determination["recommendation"] if ledger.determination else "done")
        return ledger
