from __future__ import annotations

import asyncio
import logging
from logging.handlers import RotatingFileHandler

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, ErrorEvent

from app.config import DATA_DIR, settings
from app.database import init_db
from app.handlers import admin, admin_campaigns, ads, catalog, common, start
from app.middlewares import DbSessionMiddleware, UserMiddleware

logger = logging.getLogger(__name__)


def setup_logging() -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        handlers.append(
            RotatingFileHandler(
                DATA_DIR / "bot.log",
                maxBytes=5_000_000,
                backupCount=3,
                encoding="utf-8",
            )
        )
    except OSError:
        pass
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


async def error_handler(event: ErrorEvent) -> None:
    logger.exception("Unhandled update error", exc_info=event.exception)


async def main() -> None:
    setup_logging()

    if not settings.bot_token:
        print(
            "\nBOT_TOKEN не задан.\n"
            "1. Создайте бота у @BotFather и получите токен.\n"
            "2. Откройте файл .env и заполните BOT_TOKEN и ADMIN_IDS.\n"
            "3. Запустите снова.\n"
        )
        return

    if not settings.admin_id_list:
        logger.warning("ADMIN_IDS не задан — админ-панель будет недоступна")

    await init_db()

    try:
        bot = Bot(
            token=settings.bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
    except Exception as exc:
        print(f"\nНе удалось создать бота: {exc}\nПроверьте BOT_TOKEN в .env\n")
        return

    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.message.middleware(DbSessionMiddleware())
    dispatcher.callback_query.middleware(DbSessionMiddleware())
    dispatcher.message.middleware(UserMiddleware())
    dispatcher.callback_query.middleware(UserMiddleware())

    dispatcher.include_router(start.router)
    dispatcher.include_router(catalog.router)
    dispatcher.include_router(ads.router)
    dispatcher.include_router(admin.router)
    dispatcher.include_router(admin_campaigns.router)
    dispatcher.include_router(common.router)

    dispatcher.errors.register(error_handler)

    try:
        me = await bot.get_me()
    except TelegramUnauthorizedError:
        print("\nTelegram отклонил BOT_TOKEN. Проверьте токен в .env\n")
        await bot.session.close()
        return
    except Exception as exc:
        print(f"\nНе удалось подключиться к Telegram: {exc}\n")
        await bot.session.close()
        return

    try:
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Каталог сериалов"),
                BotCommand(command="help", description="Как это работает"),
                BotCommand(command="admin", description="Админ-панель"),
            ]
        )
    except Exception:
        logger.warning("Could not set bot commands", exc_info=True)

    logger.info("Bot @%s started", me.username or me.id)
    try:
        await dispatcher.start_polling(
            bot, allowed_updates=dispatcher.resolve_used_update_types()
        )
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
