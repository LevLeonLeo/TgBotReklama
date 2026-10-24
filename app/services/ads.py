from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message

from app.config import settings
from app.keyboards import ad_keyboard
from app.models import AdCampaign, AdView
from app.repo import PAID_CHANNEL
from app.utils import esc, truncate

logger = logging.getLogger(__name__)


def build_ad_text(campaign: AdCampaign, for_caption: bool = False) -> str:
    body_limit = 760 if for_caption else 3400
    body = truncate(campaign.text or campaign.title, body_limit)
    parts = [f"<b>{esc(settings.ad_label)}</b>", "", esc(body)]

    if campaign.kind == PAID_CHANNEL:
        parts.extend(
            [
                "",
                "После перехода вернитесь в бот и нажмите «Продолжить».",
            ]
        )
    else:
        parts.extend(["", "Можно сразу нажать «Продолжить»."])

    return "\n".join(parts).strip()


async def send_ad_post(
    bot: Bot, chat_id: int, view: AdView, campaign: AdCampaign
) -> Message:
    keyboard = ad_keyboard(view.id, campaign)
    if campaign.photo_file_id:
        try:
            sent = await bot.send_photo(
                chat_id=chat_id,
                photo=campaign.photo_file_id,
                caption=build_ad_text(campaign, for_caption=True),
                reply_markup=keyboard,
            )
        except TelegramBadRequest:
            logger.warning("Ad photo failed, falling back to text", exc_info=True)
            sent = await bot.send_message(
                chat_id=chat_id,
                text=build_ad_text(campaign, for_caption=False),
                reply_markup=keyboard,
            )
    else:
        sent = await bot.send_message(
            chat_id=chat_id,
            text=build_ad_text(campaign, for_caption=False),
            reply_markup=keyboard,
        )

    view.message_id = sent.message_id
    return sent
