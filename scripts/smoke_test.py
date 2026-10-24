"""Smoke test without a real Telegram token.

Simulates updates through the real dispatcher with a fake Bot API session.
Run: .venv\\Scripts\\python.exe scripts\\smoke_test.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./data/smoke.db"
os.environ["ADMIN_IDS"] = "900001"
os.environ["BOT_TOKEN"] = "123456:TEST"

from aiogram import Bot, Dispatcher  # noqa: E402
from aiogram.client.default import DefaultBotProperties  # noqa: E402
from aiogram.client.session.base import BaseSession  # noqa: E402
from aiogram.enums import ParseMode  # noqa: E402
from aiogram.fsm.storage.memory import MemoryStorage  # noqa: E402
from aiogram.types import (  # noqa: E402
    CallbackQuery,
    Chat,
    Document,
    Message,
    PhotoSize,
    Update,
    User as TgUser,
    Video,
)
from sqlalchemy import func, select  # noqa: E402

from app.database import SessionFactory, engine, init_db  # noqa: E402
from app.handlers import admin, admin_campaigns, ads, catalog, common, start  # noqa: E402
from app.middlewares import DbSessionMiddleware, UserMiddleware  # noqa: E402
from app.models import AdCampaign, AdView, Episode, Series, Unlock, User  # noqa: E402

ADMIN_ID = 900001
USER_ID = 900002


class FakeSession(BaseSession):
    async def close(self) -> None:
        pass

    async def stream_content(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if False:
            yield b""

    async def make_request(self, bot, method, timeout=None):  # type: ignore[no-untyped-def]
        name = type(method).__name__
        if name == "GetMe":
            return TgUser(id=1, is_bot=True, first_name="Smoke", username="smoke_bot")
        if name == "AnswerCallbackQuery":
            return True
        if name.startswith("Send") or name.startswith("Edit") or name == "CopyMessage":
            chat_id = getattr(method, "chat_id", 1) or 1
            text = getattr(method, "text", None) or getattr(method, "caption", None)
            return Message(
                message_id=1000,
                date=datetime.now(),
                chat=Chat(id=chat_id, type="private"),
                text=text,
            )
        return True


def _user(user_id: int) -> TgUser:
    return TgUser(id=user_id, is_bot=False, first_name=f"User{user_id}")


def _message(update_id: int, user_id: int, text: str | None = None, **extra) -> Update:
    return Update(
        update_id=update_id,
        message=Message(
            message_id=update_id,
            date=datetime.now(),
            chat=Chat(id=user_id, type="private"),
            from_user=_user(user_id),
            text=text,
            **extra,
        ),
    )


def _callback(update_id: int, user_id: int, data: str) -> Update:
    return Update(
        update_id=update_id,
        callback_query=CallbackQuery(
            id=str(update_id),
            from_user=_user(user_id),
            chat_instance="smoke",
            data=data,
            message=Message(
                message_id=update_id,
                date=datetime.now(),
                chat=Chat(id=user_id, type="private"),
                text="menu",
            ),
        ),
    )


def _photo() -> list[PhotoSize]:
    return [PhotoSize(file_id="poster", file_unique_id="poster-u", width=10, height=10)]


def _video() -> Video:
    return Video(
        file_id="video-1",
        file_unique_id="video-u",
        width=1280,
        height=720,
        duration=60,
    )


def _document() -> Document:
    return Document(
        file_id="doc-1",
        file_unique_id="doc-u",
        file_name="episode.mp4",
        mime_type="video/mp4",
    )


async def main() -> None:
    db_path = ROOT / "data" / "smoke.db"
    if db_path.exists():
        db_path.unlink()
    await init_db()

    bot = Bot(
        token="123456:TEST",
        session=FakeSession(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(DbSessionMiddleware())
    dp.callback_query.middleware(DbSessionMiddleware())
    dp.message.middleware(UserMiddleware())
    dp.callback_query.middleware(UserMiddleware())
    for router in (
        start.router,
        catalog.router,
        ads.router,
        admin.router,
        admin_campaigns.router,
        common.router,
    ):
        dp.include_router(router)

    uid = 1
    await dp.feed_update(bot, _message(uid, ADMIN_ID, "/start"))
    uid += 1
    await dp.feed_update(bot, _message(uid, ADMIN_ID, "/admin"))
    uid += 1
    await dp.feed_update(bot, _callback(uid, ADMIN_ID, "admin:add_series"))
    uid += 1
    await dp.feed_update(bot, _message(uid, ADMIN_ID, "Test Series"))
    uid += 1
    await dp.feed_update(bot, _message(uid, ADMIN_ID, "Test description"))
    uid += 1
    await dp.feed_update(bot, _callback(uid, ADMIN_ID, "admin:skip"))
    uid += 1

    async with SessionFactory() as session:
        series_count = await session.scalar(select(func.count()).select_from(Series))
        assert series_count == 1, series_count
        series = await session.scalar(select(Series))
        series_id = series.id

    await dp.feed_update(bot, _callback(uid, ADMIN_ID, "admin:add_episode"))
    uid += 1
    await dp.feed_update(bot, _callback(uid, ADMIN_ID, f"admin:aseries:{series_id}"))
    uid += 1
    await dp.feed_update(bot, _message(uid, ADMIN_ID, video=_video()))
    uid += 1
    await dp.feed_update(bot, _message(uid, ADMIN_ID, "Free episode"))
    uid += 1
    await dp.feed_update(bot, _message(uid, ADMIN_ID, "1"))
    uid += 1
    await dp.feed_update(bot, _message(uid, ADMIN_ID, "1"))
    uid += 1
    await dp.feed_update(bot, _callback(uid, ADMIN_ID, "admin:free:1"))
    uid += 1

    await dp.feed_update(bot, _callback(uid, ADMIN_ID, "admin:add_episode"))
    uid += 1
    await dp.feed_update(bot, _callback(uid, ADMIN_ID, f"admin:aseries:{series_id}"))
    uid += 1
    await dp.feed_update(bot, _message(uid, ADMIN_ID, document=_document()))
    uid += 1
    await dp.feed_update(bot, _message(uid, ADMIN_ID, "Paid episode"))
    uid += 1
    await dp.feed_update(bot, _message(uid, ADMIN_ID, "1"))
    uid += 1
    await dp.feed_update(bot, _message(uid, ADMIN_ID, "2"))
    uid += 1
    await dp.feed_update(bot, _callback(uid, ADMIN_ID, "admin:free:0"))
    uid += 1

    await dp.feed_update(bot, _callback(uid, ADMIN_ID, "admin:add_campaign"))
    uid += 1
    await dp.feed_update(bot, _callback(uid, ADMIN_ID, "admin:ckind:paid_channel"))
    uid += 1
    await dp.feed_update(bot, _message(uid, ADMIN_ID, "Paid campaign"))
    uid += 1
    await dp.feed_update(bot, _message(uid, ADMIN_ID, "Go to channel"))
    uid += 1
    await dp.feed_update(bot, _callback(uid, ADMIN_ID, "admin:skip"))
    uid += 1
    await dp.feed_update(bot, _message(uid, ADMIN_ID, "https://t.me/example"))
    uid += 1
    await dp.feed_update(bot, _callback(uid, ADMIN_ID, "admin:skip"))
    uid += 1

    async with SessionFactory() as session:
        episodes = list((await session.scalars(select(Episode).order_by(Episode.number))).all())
        assert len(episodes) == 2, len(episodes)
        free_episode, paid_episode = episodes
        campaign = await session.scalar(select(AdCampaign))
        assert campaign is not None

    await dp.feed_update(bot, _message(uid, USER_ID, "/start"))
    uid += 1
    await dp.feed_update(bot, _callback(uid, USER_ID, f"series:{series_id}:0"))
    uid += 1
    await dp.feed_update(bot, _callback(uid, USER_ID, f"ep:{free_episode.id}"))
    uid += 1
    await dp.feed_update(bot, _callback(uid, USER_ID, f"ep:{paid_episode.id}"))
    uid += 1

    async with SessionFactory() as session:
        view = await session.scalar(select(AdView))
        assert view is not None, "ad view was not created"
        view_id = view.id

    await dp.feed_update(bot, _callback(uid, USER_ID, f"ad:continue:{view_id}"))
    uid += 1
    async with SessionFactory() as session:
        assert await session.scalar(select(func.count()).select_from(Unlock)) == 0

    await dp.feed_update(bot, _callback(uid, USER_ID, f"ad:open:{view_id}"))
    uid += 1
    await dp.feed_update(bot, _callback(uid, USER_ID, f"ad:continue:{view_id}"))
    uid += 1

    async with SessionFactory() as session:
        unlocks = await session.scalar(select(func.count()).select_from(Unlock))
        users = await session.scalar(select(func.count()).select_from(User))
        assert unlocks == 1, unlocks  # free episode is open without an unlock row
        assert users == 2, users

    await bot.session.close()
    await engine.dispose()
    db_path.unlink(missing_ok=True)
    print("SMOKE OK")


if __name__ == "__main__":
    asyncio.run(main())
