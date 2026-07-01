#!/usr/bin/env bash
# Bootstrap Ubuntu server for Ego Score Bot (Oracle Cloud / Hetzner / etc.)
set -euo pipefail

if ! command -v docker >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y git docker.io docker-compose-v2
  sudo usermod -aG docker "$USER"
  echo "Docker installed. Log out and back in, then re-run deploy.sh"
  exit 0
fi

if [ ! -f .env ]; then
  if [ -f .env.example ]; then
    cp .env.example .env
    echo "Created .env from .env.example — edit it before continuing."
    exit 1
  fi
  echo "Missing .env — copy .env.example and fill in values."
  exit 1
fi

if docker compose -f docker-compose.yml -f docker-compose.prod.yml ps -q db 2>/dev/null | grep -q .; then
  echo "Creating DB backup before deploy..."
  bash "$(dirname "$0")/backup_db.sh" || echo "Backup skipped (db not ready)."
fi

docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose ps
echo "Done. Logs: docker compose logs -f bot"
