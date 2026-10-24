from __future__ import annotations

from collections.abc import Iterable

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.config import settings
from app.models import AdCampaign, Episode, Series
from app.texts import campaign_kind_label
from app.utils import truncate


def _btn(
    text: str,
    callback_data: str | None = None,
    url: str | None = None,
) -> InlineKeyboardButton:
    if url:
        return InlineKeyboardButton(text=truncate(text, 64), url=url)
    return InlineKeyboardButton(
        text=truncate(text, 64), callback_data=callback_data or "noop"
    )


def main_menu(has_continue: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if has_continue:
        rows.append([_btn("▶️ Продолжить просмотр", "continue")])
    rows.append([_btn("📺 Каталог", "catalog")])
    rows.append([_btn("ℹ️ Помощь", "help")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def catalog_keyboard(series_list: Iterable[Series]) -> InlineKeyboardMarkup:
    rows = [
        [_btn(f"📺 {series.title}", f"series:{series.id}:0")]
        for series in series_list
    ]
    rows.append([_btn("🏠 В меню", "menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def series_keyboard(
    series_id: int,
    episodes: list[Episode],
    unlocked: set[int],
    page: int = 0,
) -> InlineKeyboardMarkup:
    page_size = max(1, settings.page_size)
    pages = max(1, (len(episodes) + page_size - 1) // page_size)
    page = min(max(page, 0), pages - 1)
    start = page * page_size
    chunk = episodes[start : start + page_size]

    rows: list[list[InlineKeyboardButton]] = []
    for episode in chunk:
        opened = episode.is_free or episode.id in unlocked
        mark = "✅" if opened else "🔒"
        rows.append(
            [
                _btn(
                    f"{mark} {episode.season}.{episode.number} {episode.title}",
                    f"ep:{episode.id}",
                )
            ]
        )

    if pages > 1:
        nav: list[InlineKeyboardButton] = []
        nav.append(
            _btn("⬅️", f"series:{series_id}:{page - 1}")
            if page > 0
            else _btn("·", "noop")
        )
        nav.append(_btn(f"{page + 1}/{pages}", "noop"))
        nav.append(
            _btn("➡️", f"series:{series_id}:{page + 1}")
            if page < pages - 1
            else _btn("·", "noop")
        )
        rows.append(nav)

    rows.append([_btn("🏠 Каталог", "catalog")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def episode_keyboard(series_id: int, next_episode_id: int | None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if next_episode_id is not None:
        rows.append([_btn("➡️ Следующая серия", f"ep:{next_episode_id}")])
    rows.append([_btn("📺 К сериям", f"series:{series_id}:0")])
    rows.append([_btn("🏠 Каталог", "catalog")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ad_keyboard(view_id: int, campaign: AdCampaign) -> InlineKeyboardMarkup:
    button_text = campaign.button_text or "Перейти в канал"
    rows = [
        [_btn(button_text, f"ad:open:{view_id}")],
        [_btn("✅ Продолжить", f"ad:continue:{view_id}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ad_keyboard_opened(
    view_id: int, campaign: AdCampaign, url: str
) -> InlineKeyboardMarkup:
    button_text = campaign.button_text or "Перейти в канал"
    rows = [
        [_btn(f"{button_text} ↗", url=url)],
        [_btn("✅ Продолжить", f"ad:continue:{view_id}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_menu() -> InlineKeyboardMarkup:
    rows = [
        [_btn("➕ Сериал", "admin:add_series"), _btn("➕ Серия", "admin:add_episode")],
        [_btn("🎬 Прикрепить видео", "admin:attach_video")],
        [_btn("📺 Сериалы", "admin:series_list")],
        [_btn("➕ Добавить рекламу", "admin:add_campaign")],
        [_btn("📣 Реклама ТГК", "admin:campaigns")],
        [_btn("📊 Статистика", "admin:stats"), _btn("📖 Инструкция", "admin:help")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_series_keyboard(series_list: Iterable[Series], prefix: str) -> InlineKeyboardMarkup:
    rows = [
        [_btn(f"📺 {series.title}", f"{prefix}{series.id}")]
        for series in series_list
    ]
    rows.append([_btn("⬅️ В админку", "admin:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_episode_keyboard(episodes: Iterable[Episode], prefix: str) -> InlineKeyboardMarkup:
    rows = [
        [
            _btn(
                f"{episode.season}.{episode.number} {episode.title}",
                f"{prefix}{episode.id}",
            )
        ]
        for episode in episodes
    ]
    rows.append([_btn("⬅️ В админку", "admin:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_series_manage_keyboard(rows_data: list[tuple[Series, int]]) -> InlineKeyboardMarkup:
    rows = []
    for series, count in rows_data:
        mark = "🟢" if series.is_active else "🔴"
        rows.append(
            [_btn(f"{mark} {series.title} ({count})", f"admin:tseries:{series.id}")]
        )
    rows.append([_btn("⬅️ В админку", "admin:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_campaigns_keyboard(campaigns: Iterable[AdCampaign]) -> InlineKeyboardMarkup:
    rows = []
    for campaign in campaigns:
        mark = "🟢" if campaign.is_active else "🔴"
        rows.append(
            [
                _btn(
                    f"{mark} {campaign.title} [{campaign_kind_label(campaign.kind)}]",
                    f"admin:tcampaign:{campaign.id}",
                )
            ]
        )
    rows.append([_btn("⬅️ В админку", "admin:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def skip_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_btn("⏭ Пропустить", "admin:skip")]]
    )


def free_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("🎁 Бесплатная", "admin:free:1"), _btn("🔒 Платная", "admin:free:0")],
            [_btn("⬅️ В админку", "admin:menu")],
        ]
    )


def campaign_kind_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("📣 Реклама ТГК", "admin:ckind:paid_channel")],
            [_btn("🔁 Затычка", "admin:ckind:filler_referral")],
            [_btn("⬅️ В админку", "admin:menu")],
        ]
    )


def back_admin() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_btn("⬅️ В админку", "admin:menu")]])
