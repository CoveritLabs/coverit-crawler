from typing import Optional, List
from uuid import UUID
from sqlalchemy import select, and_
from sqlalchemy.orm import joinedload

from .base_repository import BaseRepository
from ..models.domain import Locator, LocatorVersion


class LocatorRepository(BaseRepository):
    async def create(self, locator: Locator) -> UUID:
        locator = await self.add(locator)
        await self.session.flush()
        return locator.locator_id

    async def get_by_id(self, locator_id: UUID) -> Optional[Locator]:
        stmt = select(Locator).where(Locator.locator_id == locator_id).options(
            joinedload(Locator.locator_versions)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_app_version(self, app_version_id: UUID) -> List[Locator]:
        stmt = select(Locator).where(
            and_(Locator.app_version_id == app_version_id, Locator.active == True)
        ).order_by(Locator.created_at.desc())
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def update_locator(self, locator: Locator) -> Locator:
        return await self.update(locator)

    async def delete_locator(self, locator: Locator) -> None:
        await self.delete(locator)


class LocatorVersionRepository(BaseRepository):
    async def create(self, version: LocatorVersion) -> UUID:
        version = await self.add(version)
        await self.session.flush()
        return version.locator_version_id

    async def get_by_id(self, version_id: UUID) -> Optional[LocatorVersion]:
        stmt = select(LocatorVersion).where(LocatorVersion.locator_version_id == version_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_current_by_locator(self, locator_id: UUID) -> List[LocatorVersion]:
        stmt = select(LocatorVersion).where(
            and_(LocatorVersion.locator_id == locator_id, LocatorVersion.is_current == True)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_locator(self, locator_id: UUID) -> List[LocatorVersion]:
        stmt = select(LocatorVersion).where(
            LocatorVersion.locator_id == locator_id
        ).order_by(LocatorVersion.created_at.desc())
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def update_version(self, version: LocatorVersion) -> LocatorVersion:
        return await self.update(version)

    async def delete_version(self, version: LocatorVersion) -> None:
        await self.delete(version)
