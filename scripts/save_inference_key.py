#!/usr/bin/env python3
"""One-time: fetch the Vultr Serverless Inference sub key and persist it to .env.

Why: the account API (api.vultr.com) is IP-allowlisted and breaks on network changes.
The inference API (api.vultrinference.com) is key-based and IP-independent — so once
INFERENCE_API_KEY is in .env, the engine works from any network with no re-config.

Forces IPv4 (the account allowlist entry is an IPv4 address). Never prints the key.
Run:  python3 scripts/save_inference_key.py
"""
import json
import socket
import urllib.request
import urllib.error
from pathlib import Path

# Force IPv4 so the request matches an IPv4 allowlist entry.
_orig = socket.getaddrinfo
socket.getaddrinfo = lambda host, *a, **k: [r for r in _orig(host, *a, **k) if r[0] == socket.AF_INET]

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"
ACCT = "https://api.vultr.com/v2"


def env():
    d = {}
    if ENV.exists():
        for line in ENV.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                d[k.strip()] = v.strip()
    return d


def http(method, url, token, data=None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"raw": raw[:200]}


def main():
    e = env()
    if e.get("INFERENCE_API_KEY"):
        print("INFERENCE_API_KEY already present in .env — nothing to do.")
        return
    acct = e.get("VULTR_API_KEY", "").strip()
    if not acct:
        print("No VULTR_API_KEY in .env.")
        return
    st, body = http("GET", f"{ACCT}/inference", acct)
    if st != 200:
        print(f"Account API failed (status={st}). Is this IP allowlisted? {str(body)[:160]}")
        return
    subs = body.get("subscriptions") or body.get("inference") or []
    key = subs[0].get("api_key") if subs else None
    if not key and subs:
        _, d = http("GET", f"{ACCT}/inference/{subs[0].get('id')}", acct)
        key = (d.get("subscription") or d.get("inference") or d).get("api_key")
    if not key:
        print("Could not obtain inference key from the subscription.")
        return
    with ENV.open("a") as f:
        f.write(f"\nINFERENCE_API_KEY={key}\n")
    print(f"Saved INFERENCE_API_KEY to .env (len={len(key)}). It is IP-independent from now on.")


if __name__ == "__main__":
    main()
