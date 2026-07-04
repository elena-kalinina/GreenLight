#!/usr/bin/env python3
"""Provision GreenLight on Vultr Compute with live RAG + inference enabled.

Creates (or reuses) a small Ubuntu instance, clones the repo, writes .env with
INFERENCE_API_KEY, and starts serve.py via systemd on port 8000.

Run:  python3 scripts/deploy_vultr.py
      python3 scripts/deploy_vultr.py --region lax --label greenlight

Requires VULTR_API_KEY and INFERENCE_API_KEY in .env. Never prints secrets.
"""
from __future__ import annotations

import argparse
import base64
import json
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
ACCT = "https://api.vultr.com/v2"
REPO = "https://github.com/elena-kalinina/GreenLight.git"
DEFAULT_REGION = "lax"
DEFAULT_PLAN = "vc2-1c-1gb"
DEFAULT_LABEL = "greenlight"
DEFAULT_PORT = 80
UBUNTU_22_OS_ID = 1743

_orig_getaddrinfo = socket.getaddrinfo
socket.getaddrinfo = lambda host, *a, **k: [
    r for r in _orig_getaddrinfo(host, *a, **k) if r[0] == socket.AF_INET
]


def load_env() -> dict[str, str]:
    env = dict(**{k: v for k, v in __import__("os").environ.items()})
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip())
    return env


def http(method: str, url: str, token: str, data: dict | None = None, timeout: int = 120):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode()
            return r.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"raw": raw[:400]}


def cloud_init(inference_key: str, port: int = DEFAULT_PORT) -> str:
    key = inference_key.replace("'", "'\"'\"'")
    script = f"""#!/bin/bash
exec > /var/log/greenlight-init.log 2>&1
set -uxo pipefail
export DEBIAN_FRONTEND=noninteractive

apt-get update -y || true
apt-get install -y python3 git ca-certificates curl || exit 1

# Vultr Ubuntu images may enable ufw — open web + ssh before starting app
ufw disable || true
iptables -I INPUT -p tcp --dport 22 -j ACCEPT 2>/dev/null || true
iptables -I INPUT -p tcp --dport 80 -j ACCEPT 2>/dev/null || true
iptables -I INPUT -p tcp --dport 8000 -j ACCEPT 2>/dev/null || true

rm -rf /opt/greenlight
git clone --depth 1 {REPO} /opt/greenlight || exit 1

cat > /opt/greenlight/.env <<'ENVEOF'
INFERENCE_API_KEY={key}
GREENLIGHT_LIVE_RAG=1
GREENLIGHT_LIVE_LLM=1
ENVEOF
chmod 600 /opt/greenlight/.env

cat > /etc/systemd/system/greenlight.service <<'UNITEOF'
[Unit]
Description=GreenLight demo server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/greenlight
Environment=PORT={port}
EnvironmentFile=/opt/greenlight/.env
ExecStart=/usr/bin/python3 /opt/greenlight/serve.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNITEOF

systemctl daemon-reload
systemctl enable greenlight
systemctl restart greenlight

for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl -sf "http://127.0.0.1:{port}/frontend/index.html" >/dev/null; then
    echo OK > /var/log/greenlight-init.done
    exit 0
  fi
  sleep 5
done
systemctl status greenlight || true
journalctl -u greenlight -n 30 --no-pager || true
exit 1
"""
    return base64.b64encode(script.encode()).decode()


def pick_ssh_key(token: str) -> list[str]:
    st, body = http("GET", f"{ACCT}/ssh-keys", token)
    if st != 200:
        print(f"Warning: could not list SSH keys (HTTP {st}) — creating instance without one.")
        print("  Add a key at https://my.vultr.com/settings/#settingssshkeys for SSH access.")
        return []
    keys = body.get("ssh_keys") or []
    if not keys:
        print("Warning: no SSH keys on account — instance will use Vultr root password email.")
        return []
    return [keys[0]["id"]]


def find_instance(token: str, label: str) -> dict | None:
    st, body = http("GET", f"{ACCT}/instances", token)
    if st != 200:
        return None
    for inst in body.get("instances") or []:
        if inst.get("label") == label:
            return inst
    return None


def wait_active(token: str, instance_id: str, timeout: int = 600) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        st, body = http("GET", f"{ACCT}/instances/{instance_id}", token)
        if st == 200:
            inst = body.get("instance") or body
            status = inst.get("status", "")
            ip = inst.get("main_ip", "")
            if status == "active" and ip and ip != "0.0.0.0":
                return inst
        time.sleep(10)
    sys.exit(f"Timed out waiting for instance {instance_id} to become active.")


def main():
    ap = argparse.ArgumentParser(description="Deploy GreenLight to Vultr Compute")
    ap.add_argument("--region", default=DEFAULT_REGION, help=f"Region id (default {DEFAULT_REGION})")
    ap.add_argument("--plan", default=DEFAULT_PLAN, help=f"Plan id (default {DEFAULT_PLAN})")
    ap.add_argument("--label", default=DEFAULT_LABEL, help=f"Instance label (default {DEFAULT_LABEL})")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"HTTP port (default {DEFAULT_PORT})")
    ap.add_argument("--recreate", action="store_true", help="Delete existing instance with same label first")
    args = ap.parse_args()

    env = load_env()
    acct = env.get("VULTR_API_KEY", "").strip()
    inf = env.get("INFERENCE_API_KEY", "").strip()
    if not acct:
        sys.exit("Missing VULTR_API_KEY in .env")
    if not inf:
        sys.exit("Missing INFERENCE_API_KEY in .env — run scripts/save_inference_key.py first")

    existing = find_instance(acct, args.label)
    if existing and not args.recreate:
        inst = wait_active(acct, existing["id"], timeout=30)
        ip = inst["main_ip"]
        print(f"Instance '{args.label}' already exists — reusing {ip}")
        port = args.port
        suffix = "" if port == 80 else f":{port}"
        print(f"  Demo:  http://{ip}{suffix}/frontend/index.html")
        print("  Live Vultr RAG + inference enabled on server (.env on instance).")
        print("  Re-deploy fresh: python3 scripts/deploy_vultr.py --recreate")
        return

    if existing and args.recreate:
        http("DELETE", f"{ACCT}/instances/{existing['id']}", acct)
        print(f"Deleted existing instance {existing['id']}")
        time.sleep(5)

    ssh_ids = pick_ssh_key(acct)
    payload = {
        "region": args.region,
        "plan": args.plan,
        "os_id": UBUNTU_22_OS_ID,
        "label": args.label,
        "hostname": args.label,
        "backups": "disabled",
        "user_data": cloud_init(inf, args.port),
        "tags": ["greenlight", "raise2026"],
    }
    if ssh_ids:
        payload["sshkey_id"] = ssh_ids
    print(f"Creating {args.plan} instance in {args.region} …")
    st, body = http("POST", f"{ACCT}/instances", acct, payload)
    if st not in (201, 202):
        err = body.get("error") or json.dumps(body)[:400]
        if st == 401 and "IP" in str(err):
            print()
            print("Vultr Account API rejected this IP (api.vultr.com is allowlisted).")
            print("  1. Open https://my.vultr.com/settings/#settingsapi")
            print("  2. Add your current public IPv4 to the allowlist")
            print("  3. Re-run: python3 scripts/deploy_vultr.py")
            print()
            print("Or deploy manually from the dashboard — see docs/DEPLOY.md")
        sys.exit(f"Create instance failed (HTTP {st}): {err}")

    inst = body.get("instance") or body
    instance_id = inst["id"]
    print(f"  instance id: {instance_id}")
    print("  waiting for boot + cloud-init (3–5 min) …")
    inst = wait_active(acct, instance_id, timeout=120)
    ip = inst["main_ip"]
    port = args.port
    suffix = "" if port == 80 else f":{port}"
    url = f"http://{ip}{suffix}/frontend/index.html"
    print("  polling HTTP …")
    for i in range(24):
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as r:
                if r.status == 200:
                    break
        except Exception:
            pass
        time.sleep(10)
    else:
        print("  Warning: HTTP not up yet — cloud-init may still be running.")
        print(f"  Retry in 2 min: {url}")
    print()
    print("GreenLight deployed on Vultr Compute")
    print(f"  URL:   {url}")
    print(f"  SSH:   ssh root@{ip}")
    print(f"  Logs:  ssh root@{ip} 'journalctl -u greenlight -f'")
    print()
    print("Cloud-init installs git, clones the repo, and starts systemd.")
    print("Give it ~60s after 'active' before opening the URL.")
    print("Click Run live — this hits Vultr Turnkey RAG + Serverless Inference.")


if __name__ == "__main__":
    main()
