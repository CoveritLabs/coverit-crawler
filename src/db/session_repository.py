from typing import Optional, List
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from .base_repository import BaseRepository
from ..models.domain import CrawlSession


class CrawlSessionRepository(BaseRepository):
    async def create(self, session: CrawlSession) -> UUID:
        session = await self.add(session)
        await self.session.flush()
        return session.crawl_session_id

    async def get_by_id(self, session_id: UUID) -> Optional[CrawlSession]:
        stmt = select(CrawlSession).where(
            CrawlSession.crawl_session_id == session_id
        ).options(joinedload(CrawlSession.application_version))
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_app_version(self, app_version_id: UUID) -> List[CrawlSession]:
        stmt = select(CrawlSession).where(
            CrawlSession.app_version_id == app_version_id
        ).order_by(CrawlSession.started_at.desc())
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def update_status(self, session_id: UUID, status: str, finished_at=None) -> None:
        stmt = select(CrawlSession).where(CrawlSession.crawl_session_id == session_id)
        result = await self.session.execute(stmt)
        session = result.scalars().first()
        if session:
            session.status = status
            session.finished_at = finished_at
            await self.session.flush()

    async def update_session(self, session: CrawlSession) -> CrawlSession:
        return await self.update(session)

    async def delete_session(self, session: CrawlSession) -> None:
        await self.delete(session)
