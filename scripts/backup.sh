#!/usr/bin/env bash
# Ручной бэкап БД (в дополнение к автоматическому — см. app/worker/jobs.py::backup_database,
# который делает то же самое по расписанию BACKUP_HOUR).
# Запускать из корня проекта (там, где docker-compose.yml).
set -euo pipefail

cd "$(dirname "$0")/.."
set -a
source .env
set +a

mkdir -p backups
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
FILE="backups/vpnshop_manual_${TIMESTAMP}.sql.gz"

docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges \
  | gzip > "$FILE"

echo "Бэкап сохранён: $FILE"
