from __future__ import annotations

from app.utils import normalize_url, truncate


def test_normalize_url() -> None:
    assert normalize_url("t.me/example") == "https://t.me/example"
    assert normalize_url("@example") == "https://t.me/example"
    assert normalize_url("https://t.me/+abc") == "https://t.me/+abc"
    assert normalize_url("http://example.com") == "http://example.com"
    assert normalize_url("example.com") == "https://example.com"
    assert normalize_url("") is None
    assert normalize_url("ftp://example.com") is None
    assert normalize_url("javascript:alert(1)") is None


def test_truncate() -> None:
    assert truncate("abc", 10) == "abc"
    assert truncate("abcdefghij", 5) == "abcd…"
    assert truncate("", 5) == ""
