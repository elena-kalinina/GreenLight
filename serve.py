#!/usr/bin/env python3
"""GreenLight demo server — static UI + live SSE agent trace.

    python3 serve.py
    open http://localhost:8000/frontend/index.html
    click ▶ Run live
"""
import json
import os
import queue
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from greenlight.config import load_env  # noqa: E402

for _k, _v in load_env().items():
    os.environ.setdefault(_k, _v)

from greenlight.run import run  # noqa: E402

_DONE = object()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def do_GET(self):
        if urlparse(self.path).path == "/api/run":
            return self._stream_run(parse_qs(urlparse(self.path).query))
        return super().do_GET()

    def _stream_run(self, qs):
        delay = max(0.0, min(2.0, float(qs.get("delay", ["0.45"])[0])))
        self.protocol_version = "HTTP/1.1"
        self.close_connection = True
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        q = queue.Queue()

        def on_emit(ev):
            q.put(ev)
            time.sleep(delay)

        def worker():
            try:
                run(on_emit=on_emit)
            except Exception as exc:
                q.put({"kind": "error", "actor": "server", "text": str(exc)})
            finally:
                q.put(_DONE)

        threading.Thread(target=worker, daemon=True).start()

        try:
            while True:
                ev = q.get()
                if ev is _DONE:
                    self.wfile.write(b"event: done\ndata: {}\n\n")
                    self.wfile.flush()
                    return
                self.wfile.write(f"data: {json.dumps(ev)}\n\n".encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

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
    url = f"http://localhost:{port}/frontend/index.html"
    print("GreenLight — canvas + live agent trace")
    print(f"  mode:  {mode} (RAG={'on' if live_rag else 'off'}, LLM={'on' if live_llm else 'off'})")
    print(f"  open:  {url}")
    print("  click ▶ Run live on the page.")
    print("  Ctrl-C to stop.")
    try:
        ThreadingHTTPServer(("", port), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
