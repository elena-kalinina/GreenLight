#!/usr/bin/env python3
"""Run one full GreenLight review with live Vultr RAG (and optional LLM).

    GREENLIGHT_LIVE_RAG=1 python3 scripts/live_run.py
    GREENLIGHT_LIVE_RAG=1 GREENLIGHT_LIVE_LLM=1 python3 scripts/live_run.py

Prints timing and final determination. Exits non-zero on failure.
"""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from greenlight.config import load_env

for k, v in load_env().items():
    os.environ.setdefault(k, v)

os.environ.setdefault("GREENLIGHT_LIVE_RAG", "1")

from greenlight.run import run  # noqa: E402


def main():
    live_rag = os.environ.get("GREENLIGHT_LIVE_RAG") == "1"
    live_llm = os.environ.get("GREENLIGHT_LIVE_LLM") == "1"
    print(f"GreenLight live run — RAG={'on' if live_rag else 'off'} LLM={'on' if live_llm else 'off'}")
    t0 = time.perf_counter()
    events = []

    def on_emit(ev):
        events.append(ev)
        kind = ev.get("kind", "")
        actor = ev.get("actor", "")
        text = (ev.get("text") or "")[:100]
        print(f"  [{kind:8}] {actor:20} {text}")

    result = run(on_emit=on_emit)
    elapsed = time.perf_counter() - t0
    det = result.determination or {}
    blocked = len(result.blocked)
    ok = len(result.substantiated)
    print()
    print(f"Done in {elapsed:.1f}s — {det.get('recommendation', '?')}")
    print(f"  substantiated: {ok}/{len(result.claims)} ({blocked} blocked)")
    print(f"  confidence: {det.get('confidence', '?')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
