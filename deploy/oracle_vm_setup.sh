#!/usr/bin/env bash
# Run this ON the Oracle Cloud "Always Free" VM (Ubuntu, VM.Standard.A1.Flex
# recommended -- 2 OCPU/12GB covers postgres+redis+api+worker comfortably).
# SSH in as `ubuntu` (or `opc` on Oracle Linux images) and run:
#   curl -fsSL <raw-url-to-this-script> | bash
# or scp this file up and `bash oracle_vm_setup.sh`.
set -euo pipefail

REPO_URL="https://github.com/Beware2707/Metropulse.git"
APP_DIR="$HOME/metropulse"

echo "== Installing Docker + Compose plugin =="
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
  echo "Docker installed. You may need to log out/in once for group membership to apply."
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

echo "== Opening the OS firewall for port 8000 (Ubuntu images ship iptables rules that drop it by default) =="
sudo iptables -C INPUT -p tcp --dport 8000 -j ACCEPT 2>/dev/null || \
  sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8000 -j ACCEPT
sudo netfilter-persistent save 2>/dev/null || true

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
echo "Done. Also add an Ingress Rule for TCP port 8000 in the OCI Console:"
echo "  Networking -> Virtual Cloud Networks -> (your VCN) -> Security Lists"
echo "  -> Default Security List -> Add Ingress Rules"
echo "  Source CIDR: 0.0.0.0/0, IP Protocol: TCP, Destination Port Range: 8000"
echo
echo "Then the backend is reachable at: http://<this-VM-public-IP>:8000"
