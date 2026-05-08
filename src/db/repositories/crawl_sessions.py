import json
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.db.enums import CrawlStatus
from src.db.schemas.crawl_sessions import CrawlSession
from src.db.schemas.target_application_version import TargetApplicationVersion


async def get_session_status(session: AsyncSession, session_id: str) -> str | None:
    stmt = select(CrawlSession.status).where(CrawlSession.crawl_session_id == session_id)
    result = await session.execute(stmt)
    value = result.scalar_one_or_none()
    return str(value) if value is not None else None


async def mark_queued_running(session: AsyncSession, session_id: str) -> bool:
    stmt = (
        update(CrawlSession)
        .where(
            CrawlSession.crawl_session_id == session_id,
            CrawlSession.status == CrawlStatus.QUEUED,
        )
        .values(status=CrawlStatus.RUNNING, started_at=func.now())
    )
    result = await session.execute(stmt)
    await session.commit()
    return (result.rowcount or 0) == 1


async def mark_completed_if_running(
    session: AsyncSession,
    session_id: str,
    state_count: int,
    transition_count: int,
) -> bool:
    stmt = (
        update(CrawlSession)
        .where(
            CrawlSession.crawl_session_id == session_id,
            CrawlSession.status.in_([CrawlStatus.RUNNING, CrawlStatus.PAUSED]),
        )
        .values(
            status=CrawlStatus.COMPLETED,
            finished_at=func.now(),
            error=None,
            state_count=state_count,
            transition_count=transition_count,
        )
    )
    result = await session.execute(stmt)
    await session.commit()
    return (result.rowcount or 0) == 1


async def mark_failed_if_running(
    session: AsyncSession,
    session_id: str,
    error_message: str,
) -> bool:
    stmt = (
        update(CrawlSession)
        .where(
            CrawlSession.crawl_session_id == session_id,
            CrawlSession.status.in_([CrawlStatus.RUNNING, CrawlStatus.PAUSED]),
        )
        .values(
            status=CrawlStatus.FAILED,
            finished_at=func.now(),
            error=error_message,
        )
    )
    result = await session.execute(stmt)
    await session.commit()
    return (result.rowcount or 0) == 1


async def mark_finished_at_if_aborted(session: AsyncSession, session_id: str) -> None:
    stmt = (
        update(CrawlSession)
        .where(
            CrawlSession.crawl_session_id == session_id,
            CrawlSession.status == CrawlStatus.ABORTED,
            CrawlSession.finished_at.is_(None),
        )
        .values(finished_at=func.now())
    )
    await session.execute(stmt)
    await session.commit()


async def fetch_job_inputs(session: AsyncSession, session_id: str) -> tuple[dict[str, Any], str]:
    stmt = (
        select(CrawlSession)
        .options(
            joinedload(CrawlSession.app_version).joinedload(TargetApplicationVersion.target_application)
        )
        .where(CrawlSession.crawl_session_id == session_id)
    )

    result = await session.execute(stmt)
    crawl_session = result.scalar_one_or_none()
    if crawl_session is None:
        raise RuntimeError(f"crawl session not found: {session_id}")

    config_json = crawl_session.config
    if not isinstance(config_json, dict):
        try:
            config_json = json.loads(config_json)
        except Exception:
            config_json = {}

    base_url = str(
        getattr(
            getattr(getattr(crawl_session, "app_version", None), "target_application", None),
            "base_url",
            "",
        )
        or ""
    ).strip()
    if not base_url:
        raise RuntimeError(f"target application base_url missing for session: {session_id}")

    return config_json, base_url
