import json
from typing import Any, Optional, Tuple

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .tables import crawl_sessions, target_application_versions, target_applications


async def get_session_status(session: AsyncSession, session_id: str) -> Optional[str]:
    stmt = select(crawl_sessions.c.status).where(crawl_sessions.c.crawl_session_id == session_id)
    result = await session.execute(stmt)
    value = result.scalar_one_or_none()
    return str(value) if value is not None else None


async def mark_queued_running(session: AsyncSession, session_id: str) -> bool:
    stmt = (
        update(crawl_sessions)
        .where(
            and_(
                crawl_sessions.c.crawl_session_id == session_id,
                crawl_sessions.c.status == "QUEUED",
            )
        )
        .values(status="RUNNING", started_at=func.now())
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
        update(crawl_sessions)
        .where(
            and_(
                crawl_sessions.c.crawl_session_id == session_id,
                crawl_sessions.c.status.in_(["RUNNING", "PAUSED"]),
            )
        )
        .values(
            status="COMPLETED",
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
        update(crawl_sessions)
        .where(
            and_(
                crawl_sessions.c.crawl_session_id == session_id,
                crawl_sessions.c.status.in_(["RUNNING", "PAUSED"]),
            )
        )
        .values(
            status="FAILED",
            finished_at=func.now(),
            error=error_message,
        )
    )
    result = await session.execute(stmt)
    await session.commit()
    return (result.rowcount or 0) == 1


async def mark_finished_at_if_aborted(session: AsyncSession, session_id: str) -> None:
    stmt = (
        update(crawl_sessions)
        .where(
            and_(
                crawl_sessions.c.crawl_session_id == session_id,
                crawl_sessions.c.status == "ABORTED",
                crawl_sessions.c.finished_at.is_(None),
            )
        )
        .values(finished_at=func.now())
    )
    await session.execute(stmt)
    await session.commit()


async def fetch_job_inputs(session: AsyncSession, session_id: str) -> Tuple[dict[str, Any], str]:
    stmt = (
        select(crawl_sessions.c.config, target_applications.c.base_url)
        .select_from(
            crawl_sessions.join(
                target_application_versions,
                target_application_versions.c.id == crawl_sessions.c.app_version_id,
            ).join(
                target_applications,
                target_applications.c.id == target_application_versions.c.target_application_id,
            )
        )
        .where(crawl_sessions.c.crawl_session_id == session_id)
    )

    result = await session.execute(stmt)
    row = result.first()
    if row is None:
        raise RuntimeError(f"crawl session not found: {session_id}")

    config_json = row[0]
    if not isinstance(config_json, dict):
        try:
            config_json = json.loads(config_json)
        except Exception:
            config_json = {}

    base_url = str(row[1] or "").strip()
    if not base_url:
        raise RuntimeError(f"target application base_url missing for session: {session_id}")

    return config_json, base_url
