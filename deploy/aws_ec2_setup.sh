#!/usr/bin/env bash
# Run this ON the AWS EC2 instance (Ubuntu 24/26 LTS, t3.small recommended --
# 2 vCPU/2GiB covers postgres+redis+api+worker via docker-compose for testing).
# The security group already allows port 8000 in, so unlike the Oracle/DO
# variants this script does no OS-level firewall work.
# SSH in as `ubuntu` (AWS's default Ubuntu AMI user) and run:
#   scp -i metropulse.pem deploy/aws_ec2_setup.sh ubuntu@<instance-ip>:~
#   ssh -i metropulse.pem ubuntu@<instance-ip> 'bash aws_ec2_setup.sh'
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

echo "== Building and starting the stack =="
# Docker's own group membership may not be active in this shell yet on a
# freshly-provisioned instance -- fall back to sudo if a plain `docker`
# invocation would fail.
if docker info >/dev/null 2>&1; then
  docker compose up -d --build
else
  sudo docker compose up -d --build
fi

echo "== Waiting for the API health check =="
for _ in $(seq 1 30); do
  if curl -sf http://localhost:8000/health >/dev/null; then
    echo "API is healthy."
    break
  fi
  sleep 2
done

echo
echo "Done. The EC2 security group already allows inbound TCP 8000 from"
echo "anywhere (set during instance creation), so no further networking"
echo "changes should be needed."
echo
echo "The backend is reachable at: http://<this-instance-public-IP>:8000"
