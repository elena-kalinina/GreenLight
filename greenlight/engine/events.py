"""Event stream — every agent step emits an event for the UI trace."""
import json
from datetime import datetime, timezone
from pathlib import Path

from greenlight import config


class EventStream:
    def __init__(self, path=None, echo=True, on_emit=None):
        self.path = Path(path or config.EVENT_LOG)
        self.echo = echo
        self.on_emit = on_emit
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("")
        self.seq = 0

    def emit(self, kind, actor, **data):
        self.seq += 1
        ev = {
            "seq": self.seq,
            "ts": datetime.now(timezone.utc).isoformat(),
            "kind": kind,
            "actor": actor,
            **data,
        }
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev) + "\n")
        if self.echo:
            self._print(ev)
        if self.on_emit:
            self.on_emit(ev)
        return ev

    @staticmethod
    def _print(ev):
        icon = {
            "task": "→",
            "plan": "🧩",
            "tool": "🔧",
            "retrieval": "📄",
            "escalation": "⚠ ",
            "human_reply": "🙋",
            "claim": "🏷 ",
            "decision": "✓",
            "metric": "📈",
            "synthesis": "📋",
            "agent": "🤖",
            "agent_plan": "🧩",
            "agent_stage": "▸",
            "tool_call": "⚙",
            "opportunity": "💡",
            "error": "✗",
        }.get(ev["kind"], "·")
        detail = ev.get("text") or ev.get("summary") or ev.get("claim_id") or ""
        print(f"  {icon} [{ev['actor']:<14}] {ev['kind']:<12} {detail}")
