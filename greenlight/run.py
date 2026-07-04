#!/usr/bin/env python3
"""Run a GreenLight line review (CLI or imported by serve.py)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from greenlight.engine.events import EventStream
from greenlight.engine.coordinator import Coordinator
from greenlight.human.channel import DemoHuman


def run(*, on_emit=None):
    events = EventStream(on_emit=on_emit)
    coord = Coordinator(events, DemoHuman())
    return coord.run()


if __name__ == "__main__":
    run()
    print("\nDone — see data/events.jsonl and open serve.py in the browser.")
