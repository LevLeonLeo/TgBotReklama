#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Создан .env. Заполните BOT_TOKEN и ADMIN_IDS."
  exit 0
fi

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

. .venv/bin/activate
pip install -q -r requirements.txt
exec python run.py
