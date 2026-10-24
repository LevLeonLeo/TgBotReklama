"""Создаёт чистый zip проекта для загрузки в GitHub/GitVerse.

Запуск:
    .venv\\Scripts\\python.exe scripts\\make_github_zip.py

В архив не попадают .env, .venv, data, кэши, старые сборки и вложенные
копии проекта (например, если архив распаковали внутрь папки проекта).
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


def find_nested_projects() -> list[Path]:
    """Находит копии проекта, распакованные внутри корневой папки."""
    return [
        path
        for path in ROOT.iterdir()
        if path.is_dir()
        and (path / "run.py").is_file()
        and (path / "app").is_dir()
    ]


def main() -> None:
    if OUTPUT.exists():
        OUTPUT.unlink()

    nested = find_nested_projects()

    with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(ROOT.rglob("*")):
            if any(path == root or root in path.parents for root in nested):
                continue
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
