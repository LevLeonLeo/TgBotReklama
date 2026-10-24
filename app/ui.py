from __future__ import annotations

import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup

logger = logging.getLogger(__name__)


async def safe_answer(
    callback: CallbackQuery,
    text: str | None = None,
    show_alert: bool = False,
    url: str | None = None,
) -> bool:
    try:
        await callback.answer(text=text, show_alert=show_alert, url=url)
        return True
    except TelegramBadRequest:
        logger.debug("Could not answer callback", exc_info=True)
        return False


async def safe_edit(
    callback: CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    message = callback.message
    if message is None:
        await callback.bot.send_message(
            chat_id=callback.from_user.id, text=text, reply_markup=reply_markup
        )
        return

    if not message.photo and message.text is None:
        await callback.bot.send_message(
            chat_id=callback.from_user.id, text=text, reply_markup=reply_markup
        )
        return

    try:
        if message.photo:
            await message.edit_caption(caption=text, reply_markup=reply_markup)
        else:
            await message.edit_text(text=text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc):
            return
        logger.debug("Edit failed, sending a new message", exc_info=True)
        await callback.bot.send_message(
            chat_id=callback.from_user.id, text=text, reply_markup=reply_markup
        )
