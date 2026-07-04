#!/usr/bin/env python3
"""Quick demo assertions — run before recording."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from greenlight.engine.events import EventStream
from greenlight.engine.coordinator import Coordinator
from greenlight.human.channel import DemoHuman


def main():
    events = EventStream(echo=False)
    ledger = Coordinator(events, DemoHuman()).run()
    blocked_ids = {c.claim_id for c in ledger.blocked}
    cleared_ids = {c.claim_id for c in ledger.cleared}
    assert "C1" in blocked_ids, f"C1 should be blocked, got {blocked_ids}"
    assert "C2" in blocked_ids, f"C2 should be blocked, got {blocked_ids}"
    assert "C3" in cleared_ids, "C3 GOTS should be cleared"
    assert len(cleared_ids) == 4, f"expected 4 cleared, got {cleared_ids}"
    assert ledger.determination["confidence"] == 0.67
    assert ledger.determination["max_exposure_eur"] == 80_000_000
    c1 = next(c for c in ledger.claims if c.claim_id == "C1")
    assert c1.status == "blocked"
    assert "40" in (c1.remediation or "")
    print("demo_test OK — 4/6 cleared, 2 blocked (C1 recycled gap, C2 generic), determination ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
