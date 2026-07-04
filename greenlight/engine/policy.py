"""When the agent proceeds vs asks the human."""
PROCEED, CONFIRM, ASK = "proceed", "confirm", "ask"


def decide(action, *, blocked_claims=0, missing_evidence=False):
    if blocked_claims and action == "publish_determination":
        return CONFIRM, f"{blocked_claims} claim(s) blocked — confirm before filing"
    if missing_evidence:
        return ASK, "claim needs supplier evidence"
    if action in ("gate_line", "approve_plan"):
        return CONFIRM, "human gates the line review"
    return PROCEED, "clear"
