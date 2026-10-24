from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.keyboards import (
    catalog_keyboard,
    main_menu,
    series_keyboard,
)
from app.models import Series
from app.models import User as DbUser
from app.repo import (
    get_episode,
    get_series,
    list_episodes,
    list_series,
    unlocked_episode_ids,
)
from app.services.flow import open_episode
from app.texts import CATALOG_TITLE, MENU_TITLE, NO_CONTENT
from app.ui import safe_answer, safe_edit
from app.utils import esc, truncate

logger = logging.getLogger(__name__)
router = Router(name="catalog")


def _series_text(series: Series, episodes_count: int, opened_count: int) -> str:
    parts = [f"<b>{esc(series.title)}</b>"]
    if series.description:
        parts.extend(["", esc(truncate(series.description, 600))])
    if episodes_count:
        parts.extend(
            ["", f"Серий: <b>{episodes_count}</b> · открыто: <b>{opened_count}</b>"]
        )
    else:
        parts.extend(["", "Серий пока нет."])
    return "\n".join(parts)


async def _show_series_card(
    callback: CallbackQuery,
    series: Series,
    text: str,
    keyboard,
) -> None:
    message = callback.message
    if series.poster_file_id:
        if message is not None and message.photo:
            try:
                await message.edit_caption(caption=text, reply_markup=keyboard)
                return
            except TelegramBadRequest:
                pass
        await callback.bot.send_photo(
            chat_id=callback.from_user.id,
            photo=series.poster_file_id,
            caption=text,
            reply_markup=keyboard,
        )
        return

    if message is not None and message.text is not None:
        try:
            await message.edit_text(text=text, reply_markup=keyboard)
            return
        except TelegramBadRequest:
            pass
    await callback.bot.send_message(
        chat_id=callback.from_user.id, text=text, reply_markup=keyboard
    )


@router.callback_query(F.data == "catalog")
async def show_catalog(callback: CallbackQuery, session: AsyncSession) -> None:
    series_list = await list_series(session)
    if not series_list:
        await safe_edit(callback, NO_CONTENT, main_menu(False))
        await safe_answer(callback)
        return
    await safe_edit(callback, CATALOG_TITLE, catalog_keyboard(series_list))
    await safe_answer(callback)


@router.callback_query(F.data.startswith("series:"))
async def show_series(callback: CallbackQuery, session: AsyncSession) -> None:
    parts = (callback.data or "").split(":")
    try:
        series_id = int(parts[1])
        page = int(parts[2]) if len(parts) > 2 else 0
    except (IndexError, ValueError):
        await safe_answer(callback, "Некорректная ссылка", show_alert=True)
        return

    series = await get_series(session, series_id)
    if series is None or not series.is_active:
        await safe_answer(callback, "Сериал недоступен", show_alert=True)
        return

    episodes = await list_episodes(session, series.id)
    unlocked = await unlocked_episode_ids(session, callback.from_user.id, series.id)
    opened_count = sum(1 for ep in episodes if ep.is_free or ep.id in unlocked)
    text = _series_text(series, len(episodes), opened_count)
    keyboard = series_keyboard(series.id, episodes, unlocked, page)
    await _show_series_card(callback, series, text, keyboard)
    await safe_answer(callback)


@router.callback_query(F.data.startswith("ep:"))
async def open_episode_callback(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    parts = (callback.data or "").split(":")
    try:
        episode_id = int(parts[1])
    except (IndexError, ValueError):
        await safe_answer(callback, "Некорректная серия", show_alert=True)
        return

    episode = await get_episode(session, episode_id)
    if episode is None:
        await safe_answer(callback, "Серия не найдена", show_alert=True)
        return

    await safe_answer(callback)
    await open_episode(callback.bot, callback.from_user.id, episode_id, session)


@router.callback_query(F.data == "continue")
async def continue_watching(
    callback: CallbackQuery, session: AsyncSession, db_user: DbUser
) -> None:
    if db_user.last_episode_id is None:
        series_list = await list_series(session)
        await safe_edit(
            callback,
            CATALOG_TITLE if series_list else NO_CONTENT,
            catalog_keyboard(series_list) if series_list else main_menu(False),
        )
        await safe_answer(callback)
        return

    await safe_answer(callback)
    await open_episode(
        callback.bot, callback.from_user.id, db_user.last_episode_id, session
    )


@router.callback_query(F.data == "menu")
async def show_menu(
    callback: CallbackQuery, db_user: DbUser
) -> None:
    await safe_edit(
        callback,
        MENU_TITLE,
        main_menu(has_continue=db_user.last_episode_id is not None),
    )
    await safe_answer(callback)
