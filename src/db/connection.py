from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from typing import AsyncGenerator

from ..models.domain import Base


class DatabaseConnection:
    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self.engine = None
        self.session_factory = None

    async def connect(self) -> None:
        self.engine = create_async_engine(
            self.connection_string,
            echo=False,
            poolclass=NullPool,
        )
        self.session_factory = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def disconnect(self) -> None:
        if self.engine:
            await self.engine.dispose()

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        if not self.session_factory:
            raise RuntimeError("Database connection not initialized")
        async with self.session_factory() as session:
            yield session

    async def execute_in_session(self, func, *args, **kwargs):
        async with self.session_factory() as session:
            return await func(session, *args, **kwargs)
