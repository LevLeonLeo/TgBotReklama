from __future__ import annotations

import json
import random
import secrets

from aiogram.types import User as TgUser
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AdCampaign,
    AdClick,
    AdView,
    Episode,
    Event,
    Series,
    Unlock,
    User,
    utcnow,
)

PAID_CHANNEL = "paid_channel"
FILLER_REFERRAL = "filler_referral"


async def get_or_create_user(session: AsyncSession, tg_user: TgUser) -> User:
    user = await session.get(User, tg_user.id)
    if user is None:
        user = User(
            id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
        )
        session.add(user)
        await session.flush()
        return user

    user.username = tg_user.username
    user.first_name = tg_user.first_name
    user.last_seen_at = utcnow()
    return user


async def get_user(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


async def list_series(session: AsyncSession, only_active: bool = True) -> list[Series]:
    stmt = select(Series)
    if only_active:
        stmt = stmt.where(Series.is_active.is_(True))
    stmt = stmt.order_by(Series.sort_order, Series.id)
    return list((await session.scalars(stmt)).all())


async def get_series(session: AsyncSession, series_id: int) -> Series | None:
    return await session.get(Series, series_id)


async def list_episodes(
    session: AsyncSession, series_id: int, only_active: bool = True
) -> list[Episode]:
    stmt = select(Episode).where(Episode.series_id == series_id)
    if only_active:
        stmt = stmt.where(Episode.is_active.is_(True))
    stmt = stmt.order_by(Episode.season, Episode.number)
    return list((await session.scalars(stmt)).all())


async def get_episode(session: AsyncSession, episode_id: int) -> Episode | None:
    return await session.get(Episode, episode_id)


async def get_next_episode(session: AsyncSession, episode: Episode) -> Episode | None:
    stmt = (
        select(Episode)
        .where(
            Episode.series_id == episode.series_id,
            Episode.is_active.is_(True),
            or_(
                Episode.season > episode.season,
                and_(
                    Episode.season == episode.season,
                    Episode.number > episode.number,
                ),
            ),
        )
        .order_by(Episode.season, Episode.number)
        .limit(1)
    )
    return await session.scalar(stmt)


async def unlocked_episode_ids(
    session: AsyncSession, user_id: int, series_id: int
) -> set[int]:
    stmt = (
        select(Unlock.episode_id)
        .join(Episode, Unlock.episode_id == Episode.id)
        .where(Unlock.user_id == user_id, Episode.series_id == series_id)
    )
    return set((await session.scalars(stmt)).all())


async def is_unlocked(session: AsyncSession, user_id: int, episode_id: int) -> bool:
    stmt = select(Unlock.id).where(
        Unlock.user_id == user_id, Unlock.episode_id == episode_id
    )
    return await session.scalar(stmt) is not None


async def create_unlock(
    session: AsyncSession,
    user_id: int,
    episode_id: int,
    ad_view_id: int | None = None,
) -> Unlock:
    existing = await session.scalar(
        select(Unlock).where(
            Unlock.user_id == user_id, Unlock.episode_id == episode_id
        )
    )
    if existing is not None:
        return existing
    unlock = Unlock(user_id=user_id, episode_id=episode_id, ad_view_id=ad_view_id)
    session.add(unlock)
    await session.flush()
    return unlock


async def pick_campaign(session: AsyncSession) -> AdCampaign | None:
    campaigns = list(
        (
            await session.scalars(
                select(AdCampaign).where(AdCampaign.is_active.is_(True))
            )
        ).all()
    )
    paid = [
        c for c in campaigns if c.kind == PAID_CHANNEL and c.target_url.strip()
    ]
    filler = [
        c for c in campaigns if c.kind == FILLER_REFERRAL and c.target_url.strip()
    ]
    pool = paid or filler
    if not pool:
        return None

    best_priority = max(c.priority for c in pool)
    top = [c for c in pool if c.priority == best_priority]
    return random.choice(top)


async def create_ad_view(
    session: AsyncSession,
    user_id: int,
    campaign: AdCampaign,
    episode_id: int,
) -> AdView:
    view = AdView(
        user_id=user_id,
        campaign_id=campaign.id,
        episode_id=episode_id,
        click_token=secrets.token_urlsafe(24),
    )
    session.add(view)
    await session.flush()
    return view


async def get_ad_view(session: AsyncSession, view_id: int) -> AdView | None:
    return await session.get(AdView, view_id)


async def register_click(session: AsyncSession, view_id: int) -> AdClick | None:
    view = await session.get(AdView, view_id)
    if view is None:
        return None

    existing = await session.scalar(
        select(AdClick).where(AdClick.ad_view_id == view.id)
    )
    if existing is not None:
        return existing

    click = AdClick(
        ad_view_id=view.id,
        user_id=view.user_id,
        campaign_id=view.campaign_id,
    )
    session.add(click)
    if view.status != "completed":
        view.status = "clicked"
    await session.flush()
    return click


async def has_click(session: AsyncSession, view_id: int) -> bool:
    stmt = select(AdClick.id).where(AdClick.ad_view_id == view_id)
    return await session.scalar(stmt) is not None


async def can_unlock(session: AsyncSession, view: AdView) -> bool:
    campaign = await session.get(AdCampaign, view.campaign_id)
    if campaign is None:
        return True
    if campaign.kind == PAID_CHANNEL and campaign.require_click:
        return await has_click(session, view.id)
    return True


async def complete_ad_view(session: AsyncSession, view: AdView) -> None:
    if view.status != "completed":
        view.status = "completed"
        view.completed_at = utcnow()


async def log_event(
    session: AsyncSession, user_id: int | None, name: str, **payload: object
) -> None:
    session.add(
        Event(
            user_id=user_id,
            name=name,
            payload=json.dumps(payload, ensure_ascii=False, default=str),
        )
    )
    await session.flush()


async def get_stats(session: AsyncSession) -> dict[str, int | float]:
    users = await session.scalar(select(func.count()).select_from(User)) or 0
    series = await session.scalar(select(func.count()).select_from(Series)) or 0
    episodes = await session.scalar(select(func.count()).select_from(Episode)) or 0
    views = await session.scalar(select(func.count()).select_from(AdView)) or 0
    clicks = await session.scalar(select(func.count()).select_from(AdClick)) or 0
    unlocks = await session.scalar(select(func.count()).select_from(Unlock)) or 0
    paid_views = (
        await session.scalar(
            select(func.count())
            .select_from(AdView)
            .join(AdCampaign, AdView.campaign_id == AdCampaign.id)
            .where(AdCampaign.kind == PAID_CHANNEL)
        )
        or 0
    )
    filler_views = (
        await session.scalar(
            select(func.count())
            .select_from(AdView)
            .join(AdCampaign, AdView.campaign_id == AdCampaign.id)
            .where(AdCampaign.kind == FILLER_REFERRAL)
        )
        or 0
    )
    ctr = round(clicks / views * 100, 1) if views else 0.0
    return {
        "users": users,
        "series": series,
        "episodes": episodes,
        "views": views,
        "clicks": clicks,
        "unlocks": unlocks,
        "paid_views": paid_views,
        "filler_views": filler_views,
        "ctr": ctr,
    }


async def series_with_counts(session: AsyncSession) -> list[tuple[Series, int]]:
    stmt = (
        select(Series, func.count(Episode.id))
        .outerjoin(Episode, Episode.series_id == Series.id)
        .group_by(Series.id)
        .order_by(Series.sort_order, Series.id)
    )
    return list((await session.execute(stmt)).all())


async def list_campaigns(session: AsyncSession) -> list[AdCampaign]:
    stmt = select(AdCampaign).order_by(AdCampaign.priority.desc(), AdCampaign.id)
    return list((await session.scalars(stmt)).all())
