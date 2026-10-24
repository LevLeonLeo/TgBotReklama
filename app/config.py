from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str = ""
    admin_ids: str = ""
    support_contact: str = ""
    database_url: str = f"sqlite+aiosqlite:///{(DATA_DIR / 'bot.db').as_posix()}"
    ad_label: str = "Реклама"
    page_size: int = 12
    log_level: str = "INFO"

    @property
    def admin_id_list(self) -> list[int]:
        result: list[int] = []
        for part in self.admin_ids.replace(";", ",").split(","):
            part = part.strip()
            if part.isdigit():
                result.append(int(part))
        return result

    @property
    def support_line(self) -> str:
        if not self.support_contact:
            return ""
        return f"\n\nПоддержка: {self.support_contact}"


settings = Settings()
