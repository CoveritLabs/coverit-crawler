from src.graph.client import Neo4jClient
from src.graph.repository import GraphRepository
from src.graph.schema import init_schema


async def create_graph(uri: str, user: str, password: str):
    client = Neo4jClient(uri, user, password)
    await client.verify()
    await init_schema(client.driver)
    repo = GraphRepository(client.driver)
    return client, repo