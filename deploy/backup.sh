#!/usr/bin/env bash
#
# Онлайн-бэкап базы SQLite и .env.
# Можно запускать при работающем боте:
#   sudo -u tgbot APP_DIR=/opt/TgBotReklama bash deploy/backup.sh
#
# Или через systemd-таймер tgbot-backup.timer (ставится install_vps.sh).

set -euo pipefail
umask 077

APP_DIR="${APP_DIR:-/opt/TgBotReklama}"
BACKUP_DIR="${BACKUP_DIR:-$APP_DIR/backups}"
DB_PATH="$APP_DIR/data/bot.db"
STAMP="$(date +%Y%m%d-%H%M%S)"

mkdir -p "$BACKUP_DIR"

if [[ ! -f "$DB_PATH" ]]; then
    echo "База не найдена: $DB_PATH"
    exit 0
fi

PYTHON_BIN="$APP_DIR/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
    PYTHON_BIN="$(command -v python3)"
fi

"$PYTHON_BIN" - "$DB_PATH" "$BACKUP_DIR/bot-$STAMP.db" <<'PY'
import sqlite3
import sys

source, destination = sys.argv[1], sys.argv[2]
with sqlite3.connect(source) as src, sqlite3.connect(destination) as dst:
    src.backup(dst)
PY

if [[ -f "$APP_DIR/.env" ]]; then
    cp -p "$APP_DIR/.env" "$BACKUP_DIR/env-$STAMP.txt"
    chmod 600 "$BACKUP_DIR/env-$STAMP.txt"
fi

# Храним 14 дней
find "$BACKUP_DIR" -maxdepth 1 -type f \
    \( -name 'bot-*.db' -o -name 'env-*.txt' \) -mtime +14 -delete

echo "Бэкап готов: $BACKUP_DIR/bot-$STAMP.db"
