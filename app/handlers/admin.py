from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.filters import IsAdmin
from app.keyboards import (
    admin_episode_keyboard,
    admin_menu,
    admin_series_keyboard,
    admin_series_manage_keyboard,
    free_keyboard,
    skip_keyboard,
)
from app.models import Episode, Series
from app.repo import (
    get_series,
    get_stats,
    list_episodes,
    list_series,
    series_with_counts,
)
from app.states import AddEpisode, AddSeries, AttachVideo
from app.texts import ADMIN_HELP, ADMIN_MENU, ADMIN_STATS
from app.ui import safe_answer, safe_edit
from app.utils import esc, to_int, truncate

logger = logging.getLogger(__name__)
router = Router(name="admin")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


async def _send(
    callback: CallbackQuery,
    text: str,
    reply_markup=None,
) -> None:
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


def _extract_video(message: Message) -> tuple[str | None, bool]:
    if message.video is not None:
        return message.video.file_id, False
    if message.document is not None and (
        message.document.mime_type or ""
    ).startswith("video/"):
        return message.document.file_id, True
    return None, False


@router.message(Command("admin"))
async def admin_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(ADMIN_MENU, reply_markup=admin_menu())


@router.callback_query(F.data == "admin:menu")
async def admin_menu_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await safe_edit(callback, ADMIN_MENU, admin_menu())
    await safe_answer(callback)


# ---------------------------------------------------------------------------
# Series
# ---------------------------------------------------------------------------


@router.callback_query(F.data == "admin:add_series")
async def add_series_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AddSeries.title)
    await _send(callback, "Введите название сериала:")
    await safe_answer(callback)


@router.message(AddSeries.title)
async def add_series_title(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    if not title:
        await message.answer("Нужно текстовое название. Введите ещё раз:")
        return
    await state.update_data(title=truncate(title, 200))
    await state.set_state(AddSeries.description)
    await message.answer(
        "Введите описание сериала или пропустите:", reply_markup=skip_keyboard()
    )


@router.message(AddSeries.description)
async def add_series_description(message: Message, state: FSMContext) -> None:
    description = (message.text or "").strip()
    if not description:
        await message.answer("Введите текст описания или нажмите «Пропустить».")
        return
    await state.update_data(description=truncate(description, 1000))
    await state.set_state(AddSeries.poster)
    await message.answer(
        "Отправьте постер сериала (фото) или пропустите:",
        reply_markup=skip_keyboard(),
    )


@router.callback_query(F.data == "admin:skip", AddSeries.description)
async def add_series_skip_description(
    callback: CallbackQuery, state: FSMContext
) -> None:
    await state.update_data(description="")
    await state.set_state(AddSeries.poster)
    await _send(
        callback,
        "Отправьте постер сериала (фото) или пропустите:",
        skip_keyboard(),
    )
    await safe_answer(callback)


@router.message(AddSeries.poster, F.photo)
async def add_series_poster(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    await _create_series(message, state, session, message.photo[-1].file_id)


@router.callback_query(F.data == "admin:skip", AddSeries.poster)
async def add_series_skip_poster(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    await _create_series(callback, state, session, None)
    await safe_answer(callback)


@router.message(AddSeries.poster)
async def add_series_poster_invalid(message: Message) -> None:
    await message.answer("Отправьте фото или нажмите «Пропустить».")


async def _create_series(
    event: Message | CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    poster_file_id: str | None,
) -> None:
    data = await state.get_data()
    title = data.get("title")
    if not title:
        await _reply(event, "Не хватает названия. Начните заново: /admin")
        await state.clear()
        return

    series = Series(
        title=title,
        description=data.get("description", ""),
        poster_file_id=poster_file_id,
        is_active=True,
    )
    session.add(series)
    await session.flush()
    await state.clear()
    await _reply(
        event,
        f"✅ Сериал «{esc(truncate(title, 60))}» добавлен. Теперь добавьте серии.",
        admin_menu(),
    )


# ---------------------------------------------------------------------------
# Episodes
# ---------------------------------------------------------------------------


@router.callback_query(F.data == "admin:add_episode")
async def add_episode_start(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    series_list = await list_series(session, only_active=False)
    if not series_list:
        await safe_answer(callback, "Сначала добавьте сериал", show_alert=True)
        return
    await state.clear()
    await state.set_state(AddEpisode.series)
    await _send(
        callback,
        "Выберите сериал:",
        admin_series_keyboard(series_list, "admin:aseries:"),
    )
    await safe_answer(callback)


@router.callback_query(F.data.startswith("admin:aseries:"), AddEpisode.series)
async def add_episode_choose_series(
    callback: CallbackQuery, state: FSMContext
) -> None:
    try:
        series_id = int((callback.data or "").split(":")[2])
    except (IndexError, ValueError):
        await safe_answer(callback, "Ошибка выбора", show_alert=True)
        return
    await state.update_data(series_id=series_id)
    await state.set_state(AddEpisode.video)
    await _send(
        callback,
        "Отправьте видео серии или пропустите. Видео можно прикрепить позже.",
        skip_keyboard(),
    )
    await safe_answer(callback)


@router.message(AddEpisode.series)
async def add_episode_series_invalid(message: Message) -> None:
    await message.answer("Выберите сериал кнопкой выше или откройте /admin.")


@router.message(AddEpisode.video, F.video | F.document)
async def add_episode_video(message: Message, state: FSMContext) -> None:
    file_id, is_document = _extract_video(message)
    if file_id is None:
        await message.answer("Это не видео. Отправьте видеофайл или нажмите «Пропустить».")
        return
    await state.update_data(video_file_id=file_id, video_is_document=is_document)
    await state.set_state(AddEpisode.title)
    await message.answer("Введите название серии:")


@router.callback_query(F.data == "admin:skip", AddEpisode.video)
async def add_episode_skip_video(
    callback: CallbackQuery, state: FSMContext
) -> None:
    await state.update_data(video_file_id=None, video_is_document=False)
    await state.set_state(AddEpisode.title)
    await _send(callback, "Введите название серии:")
    await safe_answer(callback)


@router.message(AddEpisode.video)
async def add_episode_video_invalid(message: Message) -> None:
    await message.answer("Отправьте видеофайл или нажмите «Пропустить».")


@router.message(AddEpisode.title)
async def add_episode_title(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    if not title:
        await message.answer("Нужно текстовое название. Введите ещё раз:")
        return
    await state.update_data(title=truncate(title, 200))
    await state.set_state(AddEpisode.season)
    await message.answer("Введите номер сезона (например, 1):")


@router.message(AddEpisode.season)
async def add_episode_season(message: Message, state: FSMContext) -> None:
    season = to_int(message.text, 1)
    if season is None or season > 100:
        await message.answer("Введите номер сезона числом от 1 до 100:")
        return
    await state.update_data(season=season)
    await state.set_state(AddEpisode.number)
    await message.answer("Введите номер серии:")


@router.message(AddEpisode.number)
async def add_episode_number(message: Message, state: FSMContext) -> None:
    number = to_int(message.text, 1)
    if number is None or number > 1000:
        await message.answer("Введите номер серии числом от 1 до 1000:")
        return
    await state.update_data(number=number)
    await state.set_state(AddEpisode.free)
    await message.answer("Серия бесплатная?", reply_markup=free_keyboard())


@router.message(AddEpisode.free)
async def add_episode_free_invalid(message: Message) -> None:
    await message.answer("Нажмите кнопку «Бесплатная» или «Платная».")


@router.callback_query(F.data.startswith("admin:free:"), AddEpisode.free)
async def add_episode_free(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    data = await state.get_data()
    series_id = data.get("series_id")
    title = data.get("title")
    season = data.get("season")
    number = data.get("number")
    if not all([series_id, title, season, number]):
        await safe_answer(callback, "Данные потерялись. Начните заново: /admin", show_alert=True)
        await state.clear()
        return

    existing = await session.scalar(
        select(Episode).where(
            Episode.series_id == int(series_id),
            Episode.season == int(season),
            Episode.number == int(number),
        )
    )
    if existing is not None:
        await state.set_state(AddEpisode.number)
        await _send(callback, "Серия с таким номером уже есть. Введите другой номер:")
        await safe_answer(callback)
        return

    is_free = (callback.data or "").endswith(":1")
    episode = Episode(
        series_id=int(series_id),
        season=int(season),
        number=int(number),
        title=title,
        is_free=is_free,
        video_file_id=data.get("video_file_id"),
        video_is_document=bool(data.get("video_is_document")),
        is_active=True,
    )
    session.add(episode)
    await session.flush()
    await state.clear()
    await _send(
        callback,
        f"✅ Серия {season}.{number} добавлена.",
        admin_menu(),
    )
    await safe_answer(callback)


# ---------------------------------------------------------------------------
# Attach video
# ---------------------------------------------------------------------------


@router.callback_query(F.data == "admin:attach_video")
async def attach_video_start(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    series_list = await list_series(session, only_active=False)
    if not series_list:
        await safe_answer(callback, "Сначала добавьте сериал", show_alert=True)
        return
    await state.clear()
    await state.set_state(AttachVideo.series)
    await _send(
        callback,
        "Выберите сериал:",
        admin_series_keyboard(series_list, "admin:vseries:"),
    )
    await safe_answer(callback)


@router.callback_query(F.data.startswith("admin:vseries:"), AttachVideo.series)
async def attach_video_choose_series(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    try:
        series_id = int((callback.data or "").split(":")[2])
    except (IndexError, ValueError):
        await safe_answer(callback, "Ошибка выбора", show_alert=True)
        return
    episodes = await list_episodes(session, series_id, only_active=False)
    if not episodes:
        await safe_answer(callback, "В сериале нет серий", show_alert=True)
        return
    await state.update_data(series_id=series_id)
    await state.set_state(AttachVideo.episode)
    await _send(
        callback,
        "Выберите серию:",
        admin_episode_keyboard(episodes, "admin:vepisode:"),
    )
    await safe_answer(callback)


@router.callback_query(F.data.startswith("admin:vepisode:"), AttachVideo.episode)
async def attach_video_choose_episode(
    callback: CallbackQuery, state: FSMContext
) -> None:
    try:
        episode_id = int((callback.data or "").split(":")[2])
    except (IndexError, ValueError):
        await safe_answer(callback, "Ошибка выбора", show_alert=True)
        return
    await state.update_data(episode_id=episode_id)
    await state.set_state(AttachVideo.video)
    await _send(callback, "Отправьте видео для этой серии:", skip_keyboard())
    await safe_answer(callback)


@router.message(AttachVideo.video, F.video | F.document)
async def attach_video_save(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    file_id, is_document = _extract_video(message)
    if file_id is None:
        await message.answer("Это не видео. Отправьте видеофайл.")
        return
    data = await state.get_data()
    episode = await session.get(Episode, int(data.get("episode_id", 0)))
    if episode is None:
        await message.answer("Серия не найдена. Начните заново: /admin")
        await state.clear()
        return
    episode.video_file_id = file_id
    episode.video_is_document = is_document
    await session.flush()
    await state.clear()
    await message.answer("✅ Видео прикреплено.", reply_markup=admin_menu())


@router.callback_query(F.data == "admin:skip", AttachVideo.video)
async def attach_video_skip(
    callback: CallbackQuery, state: FSMContext
) -> None:
    await state.clear()
    await _send(callback, "Видео не изменено.", admin_menu())
    await safe_answer(callback)


@router.message(AttachVideo.video)
async def attach_video_invalid(message: Message) -> None:
    await message.answer("Отправьте видеофайл или нажмите «Пропустить».")


@router.message(AttachVideo.series)
async def attach_video_series_invalid(message: Message) -> None:
    await message.answer("Выберите сериал кнопкой выше или откройте /admin.")


@router.message(AttachVideo.episode)
async def attach_video_episode_invalid(message: Message) -> None:
    await message.answer("Выберите серию кнопкой выше или откройте /admin.")


# ---------------------------------------------------------------------------
# Series list, stats, help
# ---------------------------------------------------------------------------


@router.callback_query(F.data == "admin:series_list")
async def admin_series_list(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    await state.clear()
    rows_data = await series_with_counts(session)
    await safe_edit(
        callback,
        "📺 <b>Сериалы</b>\n\nНажмите на сериал, чтобы включить или выключить его.",
        admin_series_manage_keyboard(rows_data),
    )
    await safe_answer(callback)


@router.callback_query(F.data.startswith("admin:tseries:"))
async def admin_toggle_series(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    await state.clear()
    try:
        series_id = int((callback.data or "").split(":")[2])
    except (IndexError, ValueError):
        await safe_answer(callback, "Ошибка", show_alert=True)
        return
    series = await get_series(session, series_id)
    if series is None:
        await safe_answer(callback, "Сериал не найден", show_alert=True)
        return
    series.is_active = not series.is_active
    await session.flush()
    rows_data = await series_with_counts(session)
    await safe_edit(
        callback,
        "📺 <b>Сериалы</b>\n\nНажмите на сериал, чтобы включить или выключить его.",
        admin_series_manage_keyboard(rows_data),
    )
    await safe_answer(callback, "Включён" if series.is_active else "Выключен")


@router.callback_query(F.data == "admin:stats")
async def admin_stats(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    await state.clear()
    stats = await get_stats(session)
    await safe_edit(callback, ADMIN_STATS.format(**stats), admin_menu())
    await safe_answer(callback)


@router.callback_query(F.data == "admin:help")
async def admin_help(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await safe_edit(callback, ADMIN_HELP, admin_menu())
    await safe_answer(callback)
