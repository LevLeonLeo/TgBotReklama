#!/usr/bin/env bash
#
# Установка TgBotReklama на Ubuntu/Debian VPS.
#
# Использование (от root):
#   sudo bash deploy/install_vps.sh
#
# Необязательные переменные:
#   APP_DIR=/opt/TgBotReklama
#   RUN_USER=tgbot
#   SERVICE_NAME=tgbot
#   BOT_TOKEN=...
#   ADMIN_IDS=...
#   SUPPORT_CONTACT=@...
#   INSTALL_BACKUP_TIMER=1
#
# Скрипт можно запускать повторно: код обновится, data/ и .env сохранятся.

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/TgBotReklama}"
RUN_USER="${RUN_USER:-tgbot}"
SERVICE_NAME="${SERVICE_NAME:-tgbot}"
INSTALL_BACKUP_TIMER="${INSTALL_BACKUP_TIMER:-1}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="$(command -v python3 || true)"

log() { printf '\n==> %s\n' "$*"; }
fail() { printf '\nОШИБКА: %s\n' "$*" >&2; exit 1; }

[[ "${EUID}" -eq 0 ]] || fail "Запустите от root: sudo bash deploy/install_vps.sh"
[[ -n "$PYTHON_BIN" ]] || fail "python3 не найден"

if [[ -r /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    case "${ID:-}" in
        ubuntu|debian) ;;
        *) fail "Поддерживаются Ubuntu/Debian, обнаружено: ${ID:-unknown}" ;;
    esac
else
    fail "Не найден /etc/os-release"
fi

log "Обновление пакетов и установка Python"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv python3-pip rsync sqlite3 ca-certificates util-linux

if ! command -v runuser >/dev/null 2>&1; then
    fail "Не найден runuser (пакет util-linux)"
fi

if ! getent group "$RUN_USER" >/dev/null 2>&1; then
    log "Создание группы $RUN_USER"
    groupadd --system "$RUN_USER"
fi

if ! id "$RUN_USER" >/dev/null 2>&1; then
    log "Создание пользователя $RUN_USER"
    NOLOGIN="$(command -v nologin || echo /bin/false)"
    useradd --system --gid "$RUN_USER" --home-dir "$APP_DIR" --shell "$NOLOGIN" "$RUN_USER"
fi
RUN_GROUP="$(id -gn "$RUN_USER")"

run_as_user() {
    runuser -u "$RUN_USER" -- env HOME="$APP_DIR" "$@"
}

log "Копирование проекта в $APP_DIR"
mkdir -p "$APP_DIR"
if [[ "$SRC_DIR" != "$APP_DIR" ]]; then
    rsync -a --delete \
        --exclude '.venv/' \
        --exclude 'data/' \
        --exclude 'backups/' \
        --exclude '.env' \
        --exclude '*.pyc' \
        --exclude '__pycache__/' \
        --exclude '.pytest_cache/' \
        "$SRC_DIR/" "$APP_DIR/"
fi

mkdir -p "$APP_DIR/data" "$APP_DIR/backups"

# Если в исходной папке есть готовая база, а на сервере её ещё нет — переносим.
if [[ -f "$SRC_DIR/data/bot.db" && ! -f "$APP_DIR/data/bot.db" ]]; then
    log "Перенос существующей базы data/bot.db"
    install -m 600 -o "$RUN_USER" -g "$RUN_GROUP" "$SRC_DIR/data/bot.db" "$APP_DIR/data/bot.db"
fi

log "Настройка .env"
if [[ -f "$APP_DIR/.env" ]]; then
    echo "Использую существующий $APP_DIR/.env"
elif [[ -n "${BOT_TOKEN:-}" && -n "${ADMIN_IDS:-}" ]]; then
    {
        printf 'BOT_TOKEN=%s\n' "$BOT_TOKEN"
        printf 'ADMIN_IDS=%s\n' "$ADMIN_IDS"
        printf 'SUPPORT_CONTACT=%s\n' "${SUPPORT_CONTACT:-}"
        printf 'AD_LABEL=%s\n' "${AD_LABEL:-Реклама}"
        printf 'PAGE_SIZE=%s\n' "${PAGE_SIZE:-12}"
        printf 'LOG_LEVEL=%s\n' "${LOG_LEVEL:-INFO}"
    } > "$APP_DIR/.env"
elif [[ -f "$SRC_DIR/.env" ]]; then
    install -m 600 "$SRC_DIR/.env" "$APP_DIR/.env"
else
    install -m 600 "$SRC_DIR/.env.example" "$APP_DIR/.env"
fi

chown -R "$RUN_USER:$RUN_GROUP" "$APP_DIR"
chmod 600 "$APP_DIR/.env"
chmod 700 "$APP_DIR/data" "$APP_DIR/backups"

log "Виртуальное окружение и зависимости"
if [[ ! -x "$APP_DIR/.venv/bin/python" ]]; then
    run_as_user "$PYTHON_BIN" -m venv "$APP_DIR/.venv"
fi
run_as_user "$APP_DIR/.venv/bin/python" -m pip install --upgrade pip
run_as_user "$APP_DIR/.venv/bin/python" -m pip install -r "$APP_DIR/requirements.txt"

log "Инициализация базы"
run_as_user env PYTHONUTF8=1 \
    "$APP_DIR/.venv/bin/python" -c \
    "import asyncio; from app.database import init_db; asyncio.run(init_db())"

log "Служба systemd"
sed -e "s|/opt/TgBotReklama|$APP_DIR|g" \
    -e "s|^User=.*|User=$RUN_USER|" \
    -e "s|^Group=.*|Group=$RUN_GROUP|" \
    "$SRC_DIR/deploy/tgbot.service.example" \
    > "/etc/systemd/system/$SERVICE_NAME.service"

# UTF-8 для корректных русских сообщений в journalctl
if ! grep -q '^Environment=PYTHONUTF8=1' "/etc/systemd/system/$SERVICE_NAME.service"; then
    sed -i '/^Environment=PYTHONUNBUFFERED=1/a Environment=PYTHONUTF8=1' \
        "/etc/systemd/system/$SERVICE_NAME.service"
fi

systemctl daemon-reload

# Проверяем, что токен и админы заполнены, а не остались пустыми.
TOKEN_OK=0
ADMIN_OK=0
if grep -Eq '^BOT_TOKEN=[0-9]+:[A-Za-z0-9_-]+[[:space:]]*$' "$APP_DIR/.env"; then
    TOKEN_OK=1
fi
if grep -Eq '^ADMIN_IDS=[0-9]+([,;][[:space:]]*[0-9]+)*[[:space:]]*$' "$APP_DIR/.env"; then
    ADMIN_OK=1
fi

if [[ "$TOKEN_OK" -eq 0 || "$ADMIN_OK" -eq 0 ]]; then
    printf '\n'
    printf 'Файл .env создан, но BOT_TOKEN и/или ADMIN_IDS не заполнены.\n'
    printf 'Откройте: sudo nano %s/.env\n' "$APP_DIR"
    printf 'Заполните значения, затем выполните:\n'
    printf '  sudo systemctl enable --now %s\n' "$SERVICE_NAME"
    printf '  sudo journalctl -u %s -f\n' "$SERVICE_NAME"
    exit 0
fi

log "Запуск бота"
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME" || true

if [[ "$INSTALL_BACKUP_TIMER" == "1" ]]; then
    log "Ежедневный бэкап базы"
    cat > /etc/systemd/system/tgbot-backup.service <<EOF
[Unit]
Description=TgBotReklama database backup
After=${SERVICE_NAME}.service

[Service]
Type=oneshot
User=$RUN_USER
Group=$RUN_GROUP
Environment=APP_DIR=$APP_DIR
ExecStart=/bin/bash $APP_DIR/deploy/backup.sh
EOF

    cat > /etc/systemd/system/tgbot-backup.timer <<EOF
[Unit]
Description=Daily TgBotReklama backup

[Timer]
OnCalendar=*-*-* 03:30:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

    systemctl daemon-reload
    systemctl enable --now tgbot-backup.timer
fi

sleep 2
log "Статус"
systemctl --no-pager --full status "$SERVICE_NAME" || true
printf '\nПоследние строки лога:\n'
journalctl -u "$SERVICE_NAME" -n 30 --no-pager || true
printf '\nГотово. Проверьте бота в Telegram: /start и /admin.\n'
