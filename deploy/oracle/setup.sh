#!/usr/bin/env bash
# One-time setup of the TripAura backend on a fresh Ubuntu 22.04/24.04 VM
# (Oracle Cloud Always Free Ampere A1, or any Ubuntu server with ports 80/443 reachable).
#
#   curl -fsSL https://raw.githubusercontent.com/ranjanvrma/trip-aura/main/deploy/oracle/setup.sh -o setup.sh
#   bash setup.sh
#
# What it does: installs Docker + Compose + git, opens ports 80/443 in the VM firewall,
# clones the repo, asks for the few settings it needs, then builds and starts the
# backend behind Caddy (automatic HTTPS).
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/ranjanvrma/trip-aura.git}"
APP_DIR="${APP_DIR:-$HOME/trip-aura}"
ENV_FILE="$APP_DIR/deploy/oracle/.env"

say() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }

say "Installing Docker, Compose and git"
sudo apt-get update -y
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io docker-compose-v2 git curl iptables-persistent
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER" || true

say "Opening ports 80 and 443 in the VM firewall"
# Oracle's Ubuntu images ship iptables rules that reject everything except SSH.
for port in 80 443; do
  if ! sudo iptables -C INPUT -p tcp --dport "$port" -m conntrack --ctstate NEW -j ACCEPT 2>/dev/null; then
    sudo iptables -I INPUT -p tcp --dport "$port" -m conntrack --ctstate NEW -j ACCEPT
  fi
done
sudo netfilter-persistent save

say "Getting the code"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" pull --ff-only
else
  git clone "$REPO_URL" "$APP_DIR"
fi

if [ ! -f "$ENV_FILE" ]; then
  say "Configuring (deploy/oracle/.env)"
  cp "$APP_DIR/deploy/oracle/.env.example" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  PUBLIC_IP="$(curl -fsS https://api.ipify.org || true)"
  DEFAULT_DOMAIN="${PUBLIC_IP//./-}.sslip.io"
  read -rp "API domain [${DEFAULT_DOMAIN}]: " API_DOMAIN
  API_DOMAIN="${API_DOMAIN:-$DEFAULT_DOMAIN}"
  read -rp "Neon DATABASE_URL (paste, or leave empty for SQLite on this VM): " DATABASE_URL
  read -rp "Your Vercel URL, e.g. https://trip-aura.vercel.app (can be changed later): " CORS_ORIGINS
  CORS_ORIGINS="${CORS_ORIGINS:-https://trip-aura.vercel.app}"
  python3 - "$ENV_FILE" "$API_DOMAIN" "$DATABASE_URL" "$CORS_ORIGINS" <<'PY'
import sys
path, domain, db, cors = sys.argv[1:5]
lines = open(path).read().splitlines()
values = {"API_DOMAIN": domain, "DATABASE_URL": db, "CORS_ORIGINS": cors.rstrip("/")}
out = []
for line in lines:
    key = line.split("=", 1)[0]
    out.append(f"{key}={values[key]}" if key in values and not line.startswith("#") else line)
open(path, "w").write("\n".join(out) + "\n")
PY
  echo "Saved $ENV_FILE (edit it any time, then run deploy/oracle/update.sh)"
fi

say "Building and starting (first build takes about 5-10 minutes)"
cd "$APP_DIR/deploy/oracle"
sudo docker compose up -d --build

API_DOMAIN="$(grep -E '^API_DOMAIN=' "$ENV_FILE" | cut -d= -f2-)"
say "Waiting for https://${API_DOMAIN}/api/health"
for i in $(seq 1 60); do
  if curl -fsS "https://${API_DOMAIN}/api/health" >/dev/null 2>&1; then
    echo "Backend is live: https://${API_DOMAIN}  (API docs: https://${API_DOMAIN}/docs)"
    echo "Use this as VITE_API_BASE_URL in Vercel."
    exit 0
  fi
  sleep 10
done
echo "Not reachable yet. Check: sudo docker compose -f $APP_DIR/deploy/oracle/docker-compose.yml logs --tail 50"
echo "Also confirm the VCN security list allows TCP 80 and 443 from 0.0.0.0/0."
exit 1
