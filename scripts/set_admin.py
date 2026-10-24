"""Управляет списком администраторов в .env.

Примеры:
    .venv\\Scripts\\python.exe scripts\\set_admin.py 123456789
    .venv\\Scripts\\python.exe scripts\\set_admin.py 123456789 987654321
    .venv\\Scripts\\python.exe scripts\\set_admin.py --add 987654321
    .venv\\Scripts\\python.exe scripts\\set_admin.py --remove 987654321
    .venv\\Scripts\\python.exe scripts\\set_admin.py --list

После изменения перезапустите бота.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV = ROOT / ".env"
ADMIN_LINE = re.compile(r"^\s*ADMIN_IDS\s*=", re.IGNORECASE)


def dedup(values: list[int]) -> list[int]:
    result: list[int] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def parse_ids(value: str) -> list[int]:
    result: list[int] = []
    for part in value.replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit() and int(part) > 0:
            result.append(int(part))
    return dedup(result)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Добавляет, удаляет или показывает ADMIN_IDS в .env"
    )
    parser.add_argument("ids", nargs="*", help="числовые Telegram ID")
    parser.add_argument("--add", action="store_true", help="добавить к текущим")
    parser.add_argument("--remove", action="store_true", help="удалить из текущих")
    parser.add_argument("--list", action="store_true", help="показать текущие ID")
    parser.add_argument(
        "--file",
        type=Path,
        default=DEFAULT_ENV,
        help="путь к .env (по умолчанию .env в корне проекта)",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    path: Path = args.file
    if not path.exists():
        raise SystemExit(
            f"Файл не найден: {path}\n"
            "Скопируйте .env.example в .env и заполните BOT_TOKEN."
        )

    raw = path.read_bytes()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    text = raw.decode("utf-8").lstrip("\ufeff")
    lines = text.splitlines()

    current: list[int] = []
    for line in lines:
        if ADMIN_LINE.match(line):
            current.extend(parse_ids(line.split("=", 1)[1]))
    current = dedup(current)

    if args.list:
        if current:
            print("ADMIN_IDS=" + ",".join(map(str, current)))
        else:
            print("ADMIN_IDS пуст — админ-панель никому не доступна.")
        return

    if not args.ids:
        parser.error("Укажите хотя бы один ID или используйте --list")

    if args.add and args.remove:
        parser.error("Нельзя одновременно использовать --add и --remove")

    new_ids: list[int] = []
    for raw in args.ids:
        if not raw.isdigit() or int(raw) <= 0:
            parser.error(f"ID должен быть положительным числом: {raw}")
        new_ids.append(int(raw))
    new_ids = dedup(new_ids)

    if args.add:
        result = dedup(current + new_ids)
    elif args.remove:
        result = [value for value in current if value not in new_ids]
    else:
        result = new_ids

    new_line = "ADMIN_IDS=" + ",".join(map(str, result))
    output: list[str] = []
    replaced = False
    for line in lines:
        if ADMIN_LINE.match(line):
            if not replaced:
                output.append(new_line)
                replaced = True
            continue
        output.append(line)

    if not replaced:
        insert_at = len(output)
        for index, line in enumerate(output):
            if line.strip().startswith("BOT_TOKEN="):
                insert_at = index + 1
                break
        output.insert(insert_at, new_line)

    path.write_text(
        newline.join(output) + newline,
        encoding="utf-8",
        newline="",
    )

    if result:
        print("Готово: ADMIN_IDS=" + ",".join(map(str, result)))
    else:
        print("Готово: список администраторов пуст.")
    print("Перезапустите бота, чтобы изменения вступили в силу.")


if __name__ == "__main__":
    main()
