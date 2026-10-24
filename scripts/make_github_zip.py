"""Создаёт чистый zip проекта для загрузки в GitHub/GitVerse.

Запуск:
    .venv\\Scripts\\python.exe scripts\\make_github_zip.py

В архив не попадают .env, .venv, data, кэши и старые сборки.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "TgBotReklama-github.zip"

EXCLUDE_DIRS = {
    ".venv",
    "data",
    "backups",
    "__pycache__",
    ".pytest_cache",
    ".git",
}
EXCLUDE_FILES = {
    ".env",
    "TgBotReklama-github.zip",
    "TgBotReklama-vps.tar.gz",
}
EXCLUDE_SUFFIXES = {".pyc", ".pyo"}


def main() -> None:
    if OUTPUT.exists():
        OUTPUT.unlink()

    with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(ROOT.rglob("*")):
            relative = path.relative_to(ROOT)
            if any(part in EXCLUDE_DIRS for part in relative.parts):
                continue
            if path.name in EXCLUDE_FILES or path.suffix in EXCLUDE_SUFFIXES:
                continue
            if path.is_file():
                archive.write(path, relative.as_posix())

    print(f"Готово: {OUTPUT}")


if __name__ == "__main__":
    main()
