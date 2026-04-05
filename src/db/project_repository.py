from typing import Optional, List
from uuid import UUID
from sqlalchemy import select

from .base_repository import BaseRepository
from ..models.domain import Project


class ProjectRepository(BaseRepository):
    async def create(self, project: Project) -> UUID:
        project = await self.add(project)
        await self.session.flush()
        return project.project_id

    async def get_by_id(self, project_id: UUID) -> Optional[Project]:
        stmt = select(Project).where(Project.project_id == project_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Project]:
        stmt = select(Project).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def update_project(self, project: Project) -> Project:
        return await self.update(project)

    async def delete_project(self, project: Project) -> None:
        await self.delete(project)
