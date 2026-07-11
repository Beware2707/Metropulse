#!/usr/bin/env bash
# Run this ON a DigitalOcean Droplet (Ubuntu 24.04, cheapest "Basic" shared-CPU
# plan is plenty for postgres+redis+api+worker via docker-compose for testing).
# SSH in as `root` (DigitalOcean's default) and run:
#   scp deploy/digitalocean_droplet_setup.sh root@<droplet-ip>:~
#   ssh root@<droplet-ip> 'bash digitalocean_droplet_setup.sh'
set -euo pipefail

REPO_URL="https://github.com/Beware2707/Metropulse.git"
APP_DIR="$HOME/metropulse"

echo "== Installing Docker + Compose plugin =="
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi

echo "== Cloning MetroPulse =="
if [ -d "$APP_DIR" ]; then
  git -C "$APP_DIR" pull
else
  git clone "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

echo "== .env =="
if [ ! -f .env ]; then
  cat > .env <<'EOF'
# Paste your real DMRC_API_KEY below (the same one from your local .env) --
# do NOT commit this file. LOG_LEVEL/etc below are optional overrides.
DMRC_API_KEY=
LOG_LEVEL=INFO
EOF
  echo "Created .env -- edit it now and set DMRC_API_KEY before continuing:"
  echo "  nano $APP_DIR/.env"
  exit 0
fi

if ! grep -q '^DMRC_API_KEY=.\+' .env; then
  echo "DMRC_API_KEY is empty in .env -- set it first: nano $APP_DIR/.env"
  exit 1
fi

echo "== Checking the OS firewall (ufw) =="
# DigitalOcean droplets ship ufw but it's inactive by default -- unlike some
# Oracle Linux images, nothing is blocked at the OS level unless you (or a
# hardening script) enabled it. Only add a rule if it's actually active.
if command -v ufw >/dev/null 2>&1 && sudo ufw status | grep -q "Status: active"; then
  sudo ufw allow 8000/tcp
  echo "ufw was active -- added an allow rule for port 8000."
else
  echo "ufw is inactive -- nothing to open at the OS level."
fi

echo "== Building and starting the stack =="
docker compose up -d --build

echo "== Waiting for the API health check =="
for _ in $(seq 1 30); do
  if curl -sf http://localhost:8000/health >/dev/null; then
    echo "API is healthy."
    break
  fi
  sleep 2
done

echo
echo "Done. A public IP is already attached to this Droplet by default --"
echo "no extra networking setup needed unless you've attached a DigitalOcean"
echo "Cloud Firewall (Networking -> Firewalls in the dashboard). If you have"
echo "one attached, add an inbound rule: TCP, port 8000, source 0.0.0.0/0."
echo
echo "The backend is reachable at: http://<this-droplet-public-IP>:8000"
