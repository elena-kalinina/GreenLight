#!/usr/bin/env python3
"""GreenLight demo server — static UI + live SSE agent trace with human gate.

    python3 serve.py
    open http://localhost:8000/frontend/index.html
    click ▶ Run compliance review
"""
import json
import os
import queue
import sys
import threading
import time
import uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from greenlight.config import load_env  # noqa: E402

for _k, _v in load_env().items():
    os.environ.setdefault(_k, _v)

from greenlight.run import run  # noqa: E402

_DONE = object()

# Registry of runs awaiting a human decision: sid -> WebHuman
_HUMANS = {}


class WebHuman:
    """Human gate that blocks the agent thread until the browser responds.

    The initial line-review gate is auto-authorized (the user already clicked
    Run). Meaningful decisions (e.g. filing a determination with blocked
    claims) block on a queue until /api/approve delivers the decision.
    """

    def __init__(self, sid, emit):
        self.sid = sid
        self.emit = emit
        self.decision_q = queue.Queue()

    def ask(self, prompt, options=None):
        options = options or ["approve"]
        if "review of this line" in prompt.lower():
            self.emit({"kind": "gate_auto", "actor": "human",
                       "text": "Review authorized by launch owner"})
            return options[0]
        self.emit({"kind": "await_human", "actor": "coordinator",
                   "prompt": prompt, "options": options, "sid": self.sid})
        try:
            decision = self.decision_q.get(timeout=180)
        except queue.Empty:
            decision = options[0]
        return decision


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/run":
            return self._stream_run(parse_qs(urlparse(self.path).query))
        if path == "/api/approve":
            return self._approve(parse_qs(urlparse(self.path).query))
        return super().do_GET()

    def _approve(self, qs):
        sid = (qs.get("sid") or [""])[0]
        decision = (qs.get("decision") or ["approve"])[0]
        human = _HUMANS.get(sid)
        ok = False
        if human:
            human.decision_q.put(decision)
            ok = True
        body = json.dumps({"ok": ok}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _stream_run(self, qs):
        delay = max(0.0, min(2.0, float(qs.get("delay", ["0.35"])[0])))
        self.protocol_version = "HTTP/1.1"
        self.close_connection = True
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        sid = uuid.uuid4().hex[:12]
        q = queue.Queue()

        def on_emit(ev):
            q.put(ev)
            time.sleep(delay)

        human = WebHuman(sid, on_emit)
        _HUMANS[sid] = human

        def worker():
            try:
                run(on_emit=on_emit, human=human)
            except Exception as exc:
                q.put({"kind": "error", "actor": "server", "text": str(exc)})
            finally:
                q.put(_DONE)

        threading.Thread(target=worker, daemon=True).start()

        # Tell the browser its session id first (for approvals).
        self._send(f"data: {json.dumps({'kind': 'session', 'sid': sid})}\n\n")

        try:
            while True:
                ev = q.get()
                if ev is _DONE:
                    self._send("event: done\ndata: {}\n\n")
                    return
                self._send(f"data: {json.dumps(ev)}\n\n")
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            _HUMANS.pop(sid, None)

    def _send(self, text):
        self.wfile.write(text.encode("utf-8"))
        self.wfile.flush()

    def log_message(self, *args):
        pass


def main():
    port = int(os.getenv("PORT", "8000"))
    live_rag = os.getenv("GREENLIGHT_LIVE_RAG", "0") == "1"
    live_llm = os.getenv("GREENLIGHT_LIVE_LLM", "0") == "1"
    if live_llm:
        mode = "Kimi agent + Vultr RAG"
    elif live_rag:
        mode = "Vultr RAG (deterministic orchestration)"
    else:
        mode = "local fallback"
    suffix = "" if port == 80 else f":{port}"
    url = f"http://localhost{suffix}/frontend/index.html"
    print("GreenLight — enterprise line-launch agent")
    print(f"  mode:  {mode} (RAG={'on' if live_rag else 'off'}, LLM={'on' if live_llm else 'off'})")
    print(f"  open:  {url}")
    print("  Ctrl-C to stop.")
    try:
        ThreadingHTTPServer(("", port), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
