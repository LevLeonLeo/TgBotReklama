from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.config import settings
from app.keyboards import main_menu
from app.models import User as DbUser
from app.texts import MENU_TITLE, help_text
from app.ui import safe_answer, safe_edit

router = Router(name="common")


@router.message(Command("help"))
async def help_command(message: Message, db_user: DbUser) -> None:
    await message.answer(
        help_text(),
        reply_markup=main_menu(has_continue=db_user.last_episode_id is not None),
    )


@router.callback_query(F.data == "help")
async def help_callback(callback: CallbackQuery, db_user: DbUser) -> None:
    await safe_edit(
        callback,
        help_text(),
        main_menu(has_continue=db_user.last_episode_id is not None),
    )
    await safe_answer(callback)


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery) -> None:
    await safe_answer(callback)


@router.message(Command("admin"))
async def admin_denied(message: Message) -> None:
    await message.answer("Нет доступа.")


@router.callback_query(F.data.startswith("admin:"))
async def admin_callback_fallback(
    callback: CallbackQuery, db_user: DbUser
) -> None:
    if db_user.id in settings.admin_id_list:
        await safe_answer(
            callback, "Действие устарело. Откройте /admin.", show_alert=True
        )
    else:
        await safe_answer(callback, "Нет доступа", show_alert=True)


@router.message()
async def fallback(message: Message, db_user: DbUser) -> None:
    await message.answer(
        MENU_TITLE,
        reply_markup=main_menu(has_continue=db_user.last_episode_id is not None),
    )
