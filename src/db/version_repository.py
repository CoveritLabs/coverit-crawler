from typing import Optional, List
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from .base_repository import BaseRepository
from ..models.domain import ApplicationVersion


class ApplicationVersionRepository(BaseRepository):
    async def create(self, version: ApplicationVersion) -> UUID:
        version = await self.add(version)
        await self.session.flush()
        return version.app_version_id

    async def get_by_id(self, version_id: UUID) -> Optional[ApplicationVersion]:
        stmt = select(ApplicationVersion).where(
            ApplicationVersion.app_version_id == version_id
        ).options(
            joinedload(ApplicationVersion.target_application)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_app(self, app_id: UUID) -> List[ApplicationVersion]:
        stmt = select(ApplicationVersion).where(
            ApplicationVersion.app_id == app_id
        ).order_by(ApplicationVersion.captured_at.desc())
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_latest_by_app(self, app_id: UUID) -> Optional[ApplicationVersion]:
        stmt = select(ApplicationVersion).where(
            ApplicationVersion.app_id == app_id
        ).order_by(ApplicationVersion.captured_at.desc()).limit(1)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def update_version(self, version: ApplicationVersion) -> ApplicationVersion:
        return await self.update(version)

    async def delete_version(self, version: ApplicationVersion) -> None:
        await self.delete(version)
