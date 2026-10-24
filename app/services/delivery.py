from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from sqlalchemy.ext.asyncio import AsyncSession

from app.keyboards import episode_keyboard
from app.models import Episode, Series
from app.repo import get_next_episode, get_user
from app.utils import esc, truncate

logger = logging.getLogger(__name__)


def build_episode_caption(series: Series, episode: Episode) -> str:
    parts = [
        f"<b>{esc(series.title)}</b>",
        f"Сезон {episode.season}, серия {episode.number}",
    ]
    if episode.title:
        parts.extend(["", f"<b>{esc(episode.title)}</b>"])
    if episode.description:
        parts.extend(["", esc(truncate(episode.description, 500))])
    return "\n".join(parts)


async def send_episode(
    bot: Bot,
    user_id: int,
    episode: Episode,
    series: Series,
    session: AsyncSession,
) -> None:
    next_episode = await get_next_episode(session, episode)
    caption = build_episode_caption(series, episode)
    keyboard = episode_keyboard(series.id, next_episode.id if next_episode else None)

    try:
        if episode.video_file_id:
            if episode.video_is_document:
                await bot.send_document(
                    chat_id=user_id,
                    document=episode.video_file_id,
                    caption=caption,
                    reply_markup=keyboard,
                    protect_content=True,
                )
            else:
                await bot.send_video(
                    chat_id=user_id,
                    video=episode.video_file_id,
                    caption=caption,
                    reply_markup=keyboard,
                    protect_content=True,
                    supports_streaming=True,
                )
        elif episode.video_chat_id and episode.video_message_id:
            await bot.copy_message(
                chat_id=user_id,
                from_chat_id=episode.video_chat_id,
                message_id=episode.video_message_id,
                caption=caption,
                reply_markup=keyboard,
                protect_content=True,
            )
        else:
            await bot.send_message(
                chat_id=user_id,
                text="⚠️ Видео для этой серии ещё не загружено.",
            )
            return
    except TelegramForbiddenError:
        user = await get_user(session, user_id)
        if user is not None:
            user.is_blocked = True
            await session.flush()
        return
    except TelegramBadRequest:
        logger.exception("Failed to send episode %s", episode.id)
        try:
            await bot.send_message(
                chat_id=user_id,
                text="⚠️ Не удалось отправить видео. Попробуйте позже или напишите в поддержку.",
            )
        except Exception:
            pass
        return

    user = await get_user(session, user_id)
    if user is not None:
        user.last_episode_id = episode.id
        await session.flush()
