from __future__ import annotations

import html
import re
from datetime import datetime
from urllib.parse import urlparse


def truncate(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def esc(text: str | None) -> str:
    return html.escape(text or "", quote=False)


def normalize_url(value: str) -> str | None:
    value = (value or "").strip()
    if not value or any(ch.isspace() for ch in value):
        return None
    if value.startswith("@"):
        value = "https://t.me/" + value[1:]
    elif value.startswith("t.me/") or value.startswith("telegram.me/"):
        value = "https://" + value
    elif "://" not in value:
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", value):
            return None
        value = "https://" + value

    try:
        parsed = urlparse(value)
    except ValueError:
        return None

    if parsed.scheme not in {"http", "https"}:
        return None
    if not parsed.netloc or not parsed.hostname:
        return None
    return value


def to_int(value: str | None, minimum: int = 1) -> int | None:
    if value is None:
        return None
    try:
        number = int(value.strip())
    except (TypeError, ValueError):
        return None
    if number < minimum:
        return None
    return number


def format_dt(value: datetime | None) -> str:
    if value is None:
        return "—"
    return value.strftime("%d.%m.%Y %H:%M")
