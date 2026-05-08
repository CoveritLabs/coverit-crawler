from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.repositories.crawl_sessions import (
    get_session_status,
    mark_finished_at_if_aborted,
    mark_queued_running,
)


async def ensure_finished_at_if_aborted(session: AsyncSession, session_id: str) -> None:
    await mark_finished_at_if_aborted(session, session_id)


async def ensure_started_or_skip_aborted(session: AsyncSession, session_id: str) -> bool:
    status = await get_session_status(session, session_id)
    if status == "ABORTED":
        await mark_finished_at_if_aborted(session, session_id)
        return False

    started = await mark_queued_running(session, session_id)
    if started:
        return True

    status = await get_session_status(session, session_id)
    if status == "ABORTED":
        await mark_finished_at_if_aborted(session, session_id)
        return False

    if status in {"RUNNING", "PAUSED"}:
        return True

    raise RuntimeError(f"Cannot start session {session_id} with status {status}")


__all__ = [
    "ensure_finished_at_if_aborted",
    "ensure_started_or_skip_aborted",
]
