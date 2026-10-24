from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdCampaign, Episode, Series, User
from app.repo import (
    FILLER_REFERRAL,
    PAID_CHANNEL,
    can_unlock,
    create_ad_view,
    create_unlock,
    pick_campaign,
    register_click,
)


async def _base(session: AsyncSession) -> tuple[User, Series, Episode]:
    user = User(id=100, first_name="Test")
    series = Series(title="Series")
    session.add_all([user, series])
    await session.flush()

    episode = Episode(series_id=series.id, season=1, number=1, title="Episode")
    session.add(episode)
    await session.flush()
    return user, series, episode


def _paid() -> AdCampaign:
    return AdCampaign(
        kind=PAID_CHANNEL,
        title="Paid",
        text="Paid ad",
        button_text="Go",
        target_url="https://t.me/paid",
        require_click=True,
        priority=100,
        is_active=True,
    )


def _filler() -> AdCampaign:
    return AdCampaign(
        kind=FILLER_REFERRAL,
        title="Filler",
        text="Filler ad",
        button_text="Go",
        target_url="https://t.me/filler",
        require_click=False,
        priority=10,
        is_active=True,
    )


async def test_paid_campaign_has_priority(session: AsyncSession) -> None:
    _, _, _ = await _base(session)
    paid = _paid()
    filler = _filler()
    session.add_all([paid, filler])
    await session.flush()

    chosen = await pick_campaign(session)
    assert chosen is not None
    assert chosen.id == paid.id

    paid.is_active = False
    await session.flush()

    chosen = await pick_campaign(session)
    assert chosen is not None
    assert chosen.id == filler.id


async def test_paid_requires_click(session: AsyncSession) -> None:
    user, _, episode = await _base(session)
    campaign = _paid()
    session.add(campaign)
    await session.flush()

    view = await create_ad_view(session, user.id, campaign, episode.id)
    assert await can_unlock(session, view) is False

    await register_click(session, view.id)
    assert await can_unlock(session, view) is True


async def test_filler_does_not_require_click(session: AsyncSession) -> None:
    user, _, episode = await _base(session)
    campaign = _filler()
    session.add(campaign)
    await session.flush()

    view = await create_ad_view(session, user.id, campaign, episode.id)
    assert await can_unlock(session, view) is True


async def test_click_is_idempotent(session: AsyncSession) -> None:
    user, _, episode = await _base(session)
    campaign = _paid()
    session.add(campaign)
    await session.flush()

    view = await create_ad_view(session, user.id, campaign, episode.id)
    first = await register_click(session, view.id)
    second = await register_click(session, view.id)
    assert first is not None and second is not None
    assert first.id == second.id


async def test_unlock_is_idempotent(session: AsyncSession) -> None:
    user, _, episode = await _base(session)
    first = await create_unlock(session, user.id, episode.id)
    second = await create_unlock(session, user.id, episode.id)
    assert first.id == second.id
