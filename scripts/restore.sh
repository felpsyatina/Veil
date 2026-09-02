#!/usr/bin/env bash
# Восстановление БД из бэкапа. ВНИМАНИЕ: перезаписывает текущие данные.
# Использование: ./scripts/restore.sh backups/vpnshop_20260101_040000.sql.gz
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Использование: $0 <путь_к_файлу.sql.gz>" >&2
  exit 1
fi

BACKUP_FILE="$1"
if [[ ! -f "$BACKUP_FILE" ]]; then
  echo "Файл не найден: $BACKUP_FILE" >&2
  exit 1
fi

cd "$(dirname "$0")/.."
set -a
source .env
set +a

read -rp "Это ПЕРЕЗАПИШЕТ текущую базу «${POSTGRES_DB}». Продолжить? [y/N] " confirm
if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
  echo "Отменено."
  exit 0
fi

echo "Останавливаю bot/api/worker (чтобы не писали в БД во время восстановления)..."
docker compose stop bot api worker

echo "Восстанавливаю..."
gunzip -c "$BACKUP_FILE" | docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"

echo "Запускаю сервисы обратно..."
docker compose start bot api worker

echo "Восстановление завершено."
