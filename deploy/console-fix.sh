#!/bin/bash
# Paste into Vultr web console: Instance → View Console → login as root
# Fixes / starts GreenLight when the startup script did not complete.
set -uxo pipefail
export DEBIAN_FRONTEND=noninteractive

echo "=== greenlight console fix ==="
if [ -f /var/log/greenlight-init.log ]; then
  echo "--- init log (tail) ---"
  tail -30 /var/log/greenlight-init.log
fi

apt-get update -y
apt-get install -y python3 git ca-certificates curl

rm -rf /opt/greenlight
git clone --depth 1 https://github.com/elena-kalinina/GreenLight.git /opt/greenlight

# Replace YOUR_INFERENCE_KEY with the value from your local .env before pasting,
# or on the server: nano /opt/greenlight/.env
cat > /opt/greenlight/.env <<'EOF'
INFERENCE_API_KEY=YOUR_INFERENCE_KEY
GREENLIGHT_LIVE_RAG=1
GREENLIGHT_LIVE_LLM=1
EOF
chmod 600 /opt/greenlight/.env

cat > /etc/systemd/system/greenlight.service <<'EOF'
[Unit]
Description=GreenLight demo server
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/greenlight
Environment=PORT=80
EnvironmentFile=/opt/greenlight/.env
ExecStart=/usr/bin/python3 /opt/greenlight/serve.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable greenlight
systemctl restart greenlight
sleep 2
systemctl status greenlight --no-pager
curl -I http://127.0.0.1/frontend/index.html
echo "If curl shows HTTP/1.0 200 — open http://$(curl -s ifconfig.me)/frontend/index.html"
