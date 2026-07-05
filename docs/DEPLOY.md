# Deploy GreenLight on Vultr Compute

The app runs as a single Python process (`serve.py`) on a small Compute instance.
**Serverless Inference** and **Turnkey RAG** stay on Vultr's managed APIs — the box only serves the UI.

## Automated deploy (preferred)

```bash
python3 scripts/deploy_vultr.py              # default: lax, vc2-1c-1gb
python3 scripts/deploy_vultr.py --region ewr # pick region
python3 scripts/deploy_vultr.py --recreate   # replace existing instance
```

Requires in `.env`:

| Variable | Purpose |
|---|---|
| `VULTR_API_KEY` | Account API — create Compute instance |
| `INFERENCE_API_KEY` | Copied to the instance for live RAG + inference |

**IP allowlist:** `api.vultr.com` only accepts requests from IPs on your account allowlist
([Settings → API](https://my.vultr.com/settings/#settingsapi)). If deploy fails with
`Unauthorized IP address`, add your current IPv4 and retry.

`api.vultrinference.com` (inference + RAG) is **not** IP-restricted once `INFERENCE_API_KEY` is saved.

On success the script prints:

```
http://<instance-ip>:8000/frontend/index.html
```

The instance runs with `GREENLIGHT_LIVE_RAG=1` and `GREENLIGHT_LIVE_LLM=1`.

## Manual deploy (dashboard)

If the Account API is blocked, create the instance in the [Vultr dashboard](https://my.vultr.com/deploy/):

1. **Cloud Compute** → Ubuntu 22.04, **1 vCPU / 1 GB** (enough).
2. Region: closest to judges (e.g. `Los Angeles`, `New Jersey`).
3. **Startup script** → paste contents of `deploy/bootstrap.sh`, replacing
   `__INFERENCE_API_KEY__` with your inference key.
4. Open firewall: allow **TCP 8000** (Vultr instances have no firewall by default).
5. After ~3 min, open `http://<main-ip>:8000/frontend/index.html`.

SSH (optional): `ssh root@<main-ip>` then `journalctl -u greenlight -f`.

## Verify live Vultr stack (any network)

```bash
# Full agent run against live Turnkey RAG (~60–90s)
python3 scripts/live_run.py

# With live LLM calls too
GREENLIGHT_LIVE_LLM=1 python3 scripts/live_run.py

# Local server in live mode
GREENLIGHT_LIVE_RAG=1 GREENLIGHT_LIVE_LLM=1 python3 serve.py
```

## What “live” means

| Flag | Default | Live mode |
|---|---|---|
| `GREENLIGHT_LIVE_RAG=1` | off | Vultr Turnkey RAG collections (`greenlight-regulations`, `greenlight-supplier-certs`) |
| `GREENLIGHT_LIVE_LLM=1` | off | Vultr Serverless Inference (Kimi agent loop incl. **proactive claim discovery**) |

Offline mode uses the same corpus via `local_rag.py` — same declared-claim verdicts, faster, no API calls; discovery requires live Kimi agent.
Production on Compute should always run with both flags on.

## Demo flow (live)

1. ▶ **Run compliance review** — Kimi sizes commercial upside, adjudicates 6 claims, **discovers 2 ethical claim opportunities** (RDS down + RWS wool), vets them, pauses at human gate, files determination with recommended additions.
2. UI panels: agent chat · commercial metrics · claim compliance · **discovered opportunities** · human gate · launch determination.

## Update after code changes

```bash
ssh root@<ip> 'cd /opt/greenlight && git pull && systemctl restart greenlight'
```

Or re-run `python3 scripts/deploy_vultr.py --recreate`.
