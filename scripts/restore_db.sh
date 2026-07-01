#!/usr/bin/env bash
# Restore MySQL dump into running db container.
# Usage: ./scripts/restore_db.sh backups/ego_score_db_YYYYMMDD_HHMMSS.sql
set -euo pipefail

if [ $# -ne 1 ] || [ ! -f "$1" ]; then
  echo "Usage: $0 <path-to-backup.sql>"
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T db \
  mysql -u root -proot ego_score_db <"$1"

echo "Restored from: $1"
