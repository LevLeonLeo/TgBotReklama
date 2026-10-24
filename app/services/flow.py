from __future__ import annotations

import logging

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from app.repo import (
    create_ad_view,
    create_unlock,
    get_episode,
    get_series,
    get_user,
    is_unlocked,
    log_event,
    pick_campaign,
)
from app.services.ads import send_ad_post
from app.services.delivery import send_episode

logger = logging.getLogger(__name__)


async def _say(bot: Bot, user_id: int, text: str) -> None:
    try:
        await bot.send_message(chat_id=user_id, text=text)
    except Exception:
        logger.debug("Could not send message to %s", user_id, exc_info=True)


async def open_episode(
    bot: Bot, user_id: int, episode_id: int, session: AsyncSession
) -> None:
    episode = await get_episode(session, episode_id)
    if episode is None or not episode.is_active:
        await _say(bot, user_id, "⚠️ Серия недоступна.")
        return

    series = await get_series(session, episode.series_id)
    if series is None or not series.is_active:
        await _say(bot, user_id, "⚠️ Сериал временно недоступен.")
        return

    user = await get_user(session, user_id)
    if user is None:
        await _say(bot, user_id, "Нажмите /start, чтобы начать.")
        return

    if episode.is_free or await is_unlocked(session, user_id, episode.id):
        await log_event(session, user_id, "episode_open", episode_id=episode.id)
        await send_episode(bot, user_id, episode, series, session)
        return

    campaign = await pick_campaign(session)
    if campaign is None:
        await create_unlock(session, user_id, episode.id)
        await log_event(
            session, user_id, "episode_open_no_ad", episode_id=episode.id
        )
        await _say(
            bot,
            user_id,
            "📺 Реклама временно недоступна — серия открыта без рекламы.",
        )
        await send_episode(bot, user_id, episode, series, session)
        return

    view = await create_ad_view(session, user_id, campaign, episode.id)
    try:
        await send_ad_post(bot, user_id, view, campaign)
    except Exception:
        logger.exception("Could not send ad post for episode %s", episode.id)
        await create_unlock(session, user_id, episode.id)
        await log_event(
            session,
            user_id,
            "episode_open_ad_failed",
            episode_id=episode.id,
            campaign_id=campaign.id,
        )
        await _say(
            bot,
            user_id,
            "📺 Реклама временно недоступна — серия открыта без рекламы.",
        )
        await send_episode(bot, user_id, episode, series, session)
        return

    await log_event(
        session,
        user_id,
        "ad_view",
        episode_id=episode.id,
        campaign_id=campaign.id,
        kind=campaign.kind,
    )
