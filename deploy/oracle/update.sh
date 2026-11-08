#!/usr/bin/env bash
# Pull the latest code and rebuild/restart the backend. Used by the GitHub deploy workflow
# and safe to run by hand:  bash ~/trip-aura/deploy/oracle/update.sh
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$APP_DIR"
git fetch --quiet origin main
git reset --hard --quiet origin/main      # the server never has local code changes; .env is untracked
cd deploy/oracle
sudo docker compose up -d --build
sudo docker image prune -f >/dev/null
echo "Deployed $(git -C "$APP_DIR" rev-parse --short HEAD)"
