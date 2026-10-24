from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.keyboards import ad_keyboard_opened
from app.models import AdCampaign
from app.repo import (
    can_unlock,
    complete_ad_view,
    create_unlock,
    get_ad_view,
    get_episode,
    get_series,
    log_event,
    register_click,
)
from app.services.delivery import send_episode
from app.ui import safe_answer
from app.utils import normalize_url

router = Router(name="ads")


@router.callback_query(F.data.startswith("ad:open:"))
async def open_ad_link(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        view_id = int((callback.data or "").split(":")[2])
    except (IndexError, ValueError):
        await safe_answer(callback, "Некорректная ссылка", show_alert=True)
        return

    view = await get_ad_view(session, view_id)
    if view is None or view.user_id != callback.from_user.id:
        await safe_answer(callback, "Реклама не найдена", show_alert=True)
        return

    campaign = await session.get(AdCampaign, view.campaign_id)
    if campaign is None:
        await safe_answer(callback, "Реклама недоступна", show_alert=True)
        return

    url = normalize_url(campaign.target_url)
    if url is None:
        await safe_answer(callback, "Ссылка недоступна", show_alert=True)
        return

    await register_click(session, view.id)
    await log_event(
        session,
        callback.from_user.id,
        "ad_click",
        campaign_id=campaign.id,
        kind=campaign.kind,
        view_id=view.id,
    )
    await session.commit()

    markup_updated = False
    if callback.message is not None:
        try:
            await callback.message.edit_reply_markup(
                reply_markup=ad_keyboard_opened(view.id, campaign, url)
            )
            markup_updated = True
        except TelegramBadRequest:
            pass

    answered = await safe_answer(
        callback,
        "Ссылка открыта. Вернитесь и нажмите «Продолжить».",
        url=url,
    )

    if not markup_updated or not answered:
        try:
            text = (
                "Откройте канал по кнопке ниже, затем вернитесь "
                "и нажмите «Продолжить»."
            )
            keyboard = ad_keyboard_opened(view.id, campaign, url)
            if callback.message is not None:
                await callback.message.answer(text, reply_markup=keyboard)
            else:
                await callback.bot.send_message(
                    chat_id=callback.from_user.id,
                    text=text,
                    reply_markup=keyboard,
                )
        except Exception:
            pass


@router.callback_query(F.data.startswith("ad:continue:"))
async def continue_after_ad(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        view_id = int((callback.data or "").split(":")[2])
    except (IndexError, ValueError):
        await safe_answer(callback, "Некорректная ссылка", show_alert=True)
        return

    view = await get_ad_view(session, view_id)
    if view is None or view.user_id != callback.from_user.id:
        await safe_answer(callback, "Реклама не найдена", show_alert=True)
        return

    if not await can_unlock(session, view):
        await safe_answer(
            callback,
            "Сначала нажмите кнопку со ссылкой в рекламном посте, "
            "затем вернитесь и нажмите «Продолжить».",
            show_alert=True,
        )
        return

    episode = await get_episode(session, view.episode_id)
    if episode is None or not episode.is_active:
        await safe_answer(callback, "Серия недоступна", show_alert=True)
        return

    series = await get_series(session, episode.series_id)
    if series is None or not series.is_active:
        await safe_answer(callback, "Сериал недоступен", show_alert=True)
        return

    await create_unlock(
        session,
        user_id=callback.from_user.id,
        episode_id=episode.id,
        ad_view_id=view.id,
    )
    await complete_ad_view(session, view)
    await log_event(
        session,
        callback.from_user.id,
        "unlock",
        episode_id=episode.id,
        campaign_id=view.campaign_id,
        view_id=view.id,
    )
    await session.commit()

    if callback.message is not None:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except TelegramBadRequest:
            pass

    await safe_answer(callback, "Доступ открыт")
    await send_episode(callback.bot, callback.from_user.id, episode, series, session)
