from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.keyboards import catalog_keyboard, main_menu
from app.models import User as DbUser
from app.models import utcnow
from app.repo import list_series, log_event
from app.texts import CATALOG_TITLE, NO_CONTENT, WELCOME

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    command: CommandObject,
    state: FSMContext,
    session: AsyncSession,
    db_user: DbUser,
) -> None:
    await state.clear()

    payload = (command.args or "").strip()
    if payload:
        db_user.source = payload[:128]
    db_user.last_seen_at = utcnow()

    await log_event(session, db_user.id, "start", source=payload[:128])

    await message.answer(
        WELCOME,
        reply_markup=main_menu(has_continue=db_user.last_episode_id is not None),
    )

    series_list = await list_series(session)
    if series_list:
        await message.answer(CATALOG_TITLE, reply_markup=catalog_keyboard(series_list))
    else:
        extra = ""
        if db_user.id in settings.admin_id_list:
            extra = "\n\nАдмин: /admin"
        await message.answer(NO_CONTENT + extra)
