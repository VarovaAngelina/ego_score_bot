#!/usr/bin/env bash
# Dump MySQL from docker compose (run before git pull / deploy).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

mkdir -p backups
OUT="backups/ego_score_db_$(date +%Y%m%d_%H%M%S).sql"

docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T db \
  mysqldump -u root -proot --single-transaction --routines --triggers ego_score_db >"$OUT"

echo "Backup saved: $OUT"
