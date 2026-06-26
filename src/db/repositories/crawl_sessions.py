import json
from datetime import datetime
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
    if value is None:
        return None
    enum_value = getattr(value, "value", None)
    return str(enum_value if enum_value is not None else value)


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


async def update_counts_if_active(
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


async def mark_aborted_if_active(session: AsyncSession, session_id: str) -> bool:
    stmt = (
        update(CrawlSession)
        .where(
            CrawlSession.crawl_session_id == session_id,
            CrawlSession.status.in_(
                [
                    CrawlStatus.NEW,
                    CrawlStatus.QUEUED,
                    CrawlStatus.RUNNING,
                    CrawlStatus.PAUSED,
                ]
            ),
        )
        .values(status=CrawlStatus.ABORTED, finished_at=func.now())
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


async def fetch_job_inputs(session: AsyncSession, session_id: str) -> tuple[dict[str, Any], str, str, int, int]:
    stmt = (
        select(CrawlSession)
        .options(joinedload(CrawlSession.app_version).joinedload(TargetApplicationVersion.target_application))
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

    base_url = str(crawl_session.base_url_snapshot or "").strip()
    if not base_url:
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

    app_version_id = str(crawl_session.app_version_id or "").strip()
    if not app_version_id:
        raise RuntimeError(f"app_version_id missing for session: {session_id}")

    return (
        config_json,
        base_url,
        app_version_id,
        int(crawl_session.state_count or 0),
        int(crawl_session.transition_count or 0),
    )


async def fetch_graph_id(session: AsyncSession, session_id: str) -> str:
    stmt = select(CrawlSession.app_version_id).where(CrawlSession.crawl_session_id == session_id)
    result = await session.execute(stmt)
    value = result.scalar_one_or_none()
    graph_id = str(value or "").strip()
    if not graph_id:
        raise RuntimeError(f"app_version_id missing for session: {session_id}")
    return graph_id


async def fetch_started_at(session: AsyncSession, session_id: str) -> datetime | None:
    stmt = select(CrawlSession.started_at).where(CrawlSession.crawl_session_id == session_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
