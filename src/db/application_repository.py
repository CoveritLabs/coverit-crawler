from typing import Optional, List
from uuid import UUID
from sqlalchemy import select

from .base_repository import BaseRepository
from ..models.domain import TargetApplication


class TargetApplicationRepository(BaseRepository):
    async def create(self, app: TargetApplication) -> UUID:
        app = await self.add(app)
        await self.session.flush()
        return app.app_id

    async def get_by_id(self, app_id: UUID) -> Optional[TargetApplication]:
        stmt = select(TargetApplication).where(TargetApplication.app_id == app_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_project(self, project_id: UUID) -> List[TargetApplication]:
        stmt = select(TargetApplication).where(TargetApplication.project_id == project_id)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def update_app(self, app: TargetApplication) -> TargetApplication:
        return await self.update(app)

    async def delete_app(self, app: TargetApplication) -> None:
        await self.delete(app)
