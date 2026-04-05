from sqlalchemy.ext.asyncio import AsyncSession

from .project_repository import ProjectRepository
from .application_repository import TargetApplicationRepository
from .version_repository import ApplicationVersionRepository
from .session_repository import CrawlSessionRepository
from .locator_repository import LocatorRepository, LocatorVersionRepository


class Repository:
    def __init__(self, session: AsyncSession):
        self.projects = ProjectRepository(session)
        self.applications = TargetApplicationRepository(session)
        self.application_versions = ApplicationVersionRepository(session)
        self.crawl_sessions = CrawlSessionRepository(session)
        self.locators = LocatorRepository(session)
        self.locator_versions = LocatorVersionRepository(session)
        self._session = session

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
