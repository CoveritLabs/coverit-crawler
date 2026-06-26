from neo4j import AsyncDriver, AsyncGraphDatabase


class Neo4jClient:
    def __init__(self, uri: str, user: str, password: str):
        self._driver: AsyncDriver = AsyncGraphDatabase.driver(
            uri,
            auth=(user, password),
        )

    @property
    def driver(self) -> AsyncDriver:
        return self._driver

    async def verify(self) -> None:
        await self._driver.verify_connectivity()

    async def close(self) -> None:
        await self._driver.close()
