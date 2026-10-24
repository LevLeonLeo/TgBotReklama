from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class AddSeries(StatesGroup):
    title = State()
    description = State()
    poster = State()


class AddEpisode(StatesGroup):
    series = State()
    video = State()
    title = State()
    season = State()
    number = State()
    free = State()


class AttachVideo(StatesGroup):
    series = State()
    episode = State()
    video = State()


class AddCampaign(StatesGroup):
    kind = State()
    title = State()
    text = State()
    button_text = State()
    target_url = State()
    photo = State()
