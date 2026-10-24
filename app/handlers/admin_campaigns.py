from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.filters import IsAdmin
from app.keyboards import (
    admin_campaigns_keyboard,
    admin_menu,
    campaign_kind_keyboard,
    skip_keyboard,
)
from app.models import AdCampaign
from app.repo import FILLER_REFERRAL, PAID_CHANNEL, list_campaigns
from app.states import AddCampaign
from app.texts import campaign_kind_label
from app.ui import safe_answer, safe_edit
from app.utils import esc, normalize_url, truncate

logger = logging.getLogger(__name__)
router = Router(name="admin_campaigns")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


async def _send(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    if callback.message is not None:
        await callback.message.answer(text, reply_markup=reply_markup)
    else:
        await callback.bot.send_message(
            chat_id=callback.from_user.id, text=text, reply_markup=reply_markup
        )


async def _reply(event: Message | CallbackQuery, text: str, reply_markup=None) -> None:
    if isinstance(event, CallbackQuery):
        await _send(event, text, reply_markup)
    else:
        await event.answer(text, reply_markup=reply_markup)


@router.callback_query(F.data == "admin:add_campaign")
async def add_campaign_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AddCampaign.kind)
    await _send(
        callback,
        "Выберите тип рекламы:\n\n"
        "📣 <b>Реклама ТГК</b> — клик по ссылке обязателен.\n"
        "🔁 <b>Затычка</b> — клик не обязателен, серия открывается сразу.",
        campaign_kind_keyboard(),
    )
    await safe_answer(callback)


@router.callback_query(F.data.startswith("admin:ckind:"), AddCampaign.kind)
async def add_campaign_kind(callback: CallbackQuery, state: FSMContext) -> None:
    kind = (callback.data or "").split(":")[2]
    if kind not in {PAID_CHANNEL, FILLER_REFERRAL}:
        await safe_answer(callback, "Неизвестный тип", show_alert=True)
        return
    await state.update_data(kind=kind)
    await state.set_state(AddCampaign.title)
    await _send(callback, "Введите название рекламы для админки:")
    await safe_answer(callback)


@router.message(AddCampaign.kind)
async def add_campaign_kind_invalid(message: Message) -> None:
    await message.answer("Выберите тип рекламы кнопкой выше.")


@router.message(AddCampaign.title)
async def add_campaign_title(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    if not title:
        await message.answer("Нужно текстовое название. Введите ещё раз:")
        return
    await state.update_data(title=truncate(title, 200))
    await state.set_state(AddCampaign.text)
    await message.answer("Введите текст рекламного поста:")


@router.message(AddCampaign.text)
async def add_campaign_text(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("Нужен текст рекламного поста. Введите ещё раз:")
        return
    await state.update_data(text=truncate(text, 3000))
    await state.set_state(AddCampaign.button_text)
    await message.answer(
        "Введите текст кнопки (например, «Перейти в канал») или пропустите:",
        reply_markup=skip_keyboard(),
    )


@router.message(AddCampaign.button_text)
async def add_campaign_button_text(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("Введите текст кнопки или нажмите «Пропустить».")
        return
    await state.update_data(button_text=truncate(text, 64))
    await state.set_state(AddCampaign.target_url)
    await message.answer("Введите ссылку: https://t.me/... или https://...")


@router.callback_query(F.data == "admin:skip", AddCampaign.button_text)
async def add_campaign_skip_button(
    callback: CallbackQuery, state: FSMContext
) -> None:
    await state.update_data(button_text="Перейти в канал")
    await state.set_state(AddCampaign.target_url)
    await _send(callback, "Введите ссылку: https://t.me/... или https://...")
    await safe_answer(callback)


@router.message(AddCampaign.target_url)
async def add_campaign_url(message: Message, state: FSMContext) -> None:
    url = normalize_url(message.text or "")
    if url is None:
        await message.answer(
            "Ссылка должна начинаться с http:// или https://. Введите ещё раз:"
        )
        return
    await state.update_data(target_url=url)
    await state.set_state(AddCampaign.photo)
    await message.answer(
        "Отправьте фото для рекламного поста или пропустите:",
        reply_markup=skip_keyboard(),
    )


@router.message(AddCampaign.photo, F.photo)
async def add_campaign_photo(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    await _create_campaign(message, state, session, message.photo[-1].file_id)


@router.callback_query(F.data == "admin:skip", AddCampaign.photo)
async def add_campaign_skip_photo(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    await _create_campaign(callback, state, session, None)
    await safe_answer(callback)


@router.message(AddCampaign.photo)
async def add_campaign_photo_invalid(message: Message) -> None:
    await message.answer("Отправьте фото или нажмите «Пропустить».")


async def _create_campaign(
    event: Message | CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    photo_file_id: str | None,
) -> None:
    data = await state.get_data()
    kind = data.get("kind")
    title = data.get("title")
    text = data.get("text")
    target_url = data.get("target_url")
    if not all([kind, title, text, target_url]):
        await _reply(event, "Данные потерялись. Начните заново: /admin")
        await state.clear()
        return

    campaign = AdCampaign(
        kind=kind,
        title=title,
        text=text,
        button_text=data.get("button_text", "Перейти в канал"),
        target_url=target_url,
        photo_file_id=photo_file_id,
        require_click=kind == PAID_CHANNEL,
        priority=100 if kind == PAID_CHANNEL else 10,
        is_active=True,
    )
    session.add(campaign)
    await session.flush()
    await state.clear()

    kind_label = campaign_kind_label(campaign.kind)
    click_note = "обязателен" if campaign.require_click else "не обязателен"
    await _reply(
        event,
        f"✅ {kind_label} «{esc(truncate(title, 60))}» добавлена.\n"
        f"Клик: <b>{click_note}</b>\n\n"
        "Проверьте её с другого аккаунта.",
        admin_menu(),
    )


@router.callback_query(F.data == "admin:campaigns")
async def admin_campaigns(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    await state.clear()
    campaigns = await list_campaigns(session)
    if not campaigns:
        await safe_edit(
            callback,
            "📣 <b>Реклама ТГК</b>\n\nПока нет ни одной рекламы.",
            admin_campaigns_keyboard([]),
        )
    else:
        await safe_edit(
            callback,
            "📣 <b>Реклама ТГК</b>\n\nНажмите на рекламу, чтобы включить или выключить её.",
            admin_campaigns_keyboard(campaigns),
        )
    await safe_answer(callback)


@router.callback_query(F.data.startswith("admin:tcampaign:"))
async def admin_toggle_campaign(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    await state.clear()
    try:
        campaign_id = int((callback.data or "").split(":")[2])
    except (IndexError, ValueError):
        await safe_answer(callback, "Ошибка", show_alert=True)
        return
    campaign = await session.get(AdCampaign, campaign_id)
    if campaign is None:
        await safe_answer(callback, "Реклама не найдена", show_alert=True)
        return
    campaign.is_active = not campaign.is_active
    await session.flush()
    campaigns = await list_campaigns(session)
    await safe_edit(
        callback,
        "📣 <b>Реклама ТГК</b>\n\nНажмите на рекламу, чтобы включить или выключить её.",
        admin_campaigns_keyboard(campaigns),
    )
    await safe_answer(callback, "Включена" if campaign.is_active else "Выключена")
