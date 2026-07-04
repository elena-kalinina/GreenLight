#!/bin/bash
# Vultr startup script — paste into "Startup Script" when creating an instance.
# Replace __INFERENCE_API_KEY__ with your inference key before pasting.
set -euxo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 git ca-certificates
rm -rf /opt/greenlight
git clone --depth 1 https://github.com/elena-kalinina/GreenLight.git /opt/greenlight
cat > /opt/greenlight/.env <<'ENVEOF'
INFERENCE_API_KEY=__INFERENCE_API_KEY__
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
Environment=PORT=8000
EnvironmentFile=/opt/greenlight/.env
ExecStart=/usr/bin/python3 /opt/greenlight/serve.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNITEOF
systemctl daemon-reload
systemctl enable greenlight
systemctl restart greenlight
