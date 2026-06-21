from __future__ import annotations

from arq.worker import run_worker

from src import config
from src.db.database import create_engine, create_sessionmaker
from src.workers.main import _redis_settings_from_url, arq_job_serializer, arq_job_deserializer
from src.workers.jobs.flows_job import run_find_all_flows
from src.graph import Neo4jGraphBuilder 

async def startup(ctx: dict) -> None:
    db_url = config.DATABASE_URL
    if not db_url:
        raise ValueError("DATABASE_URL is required")
    
    engine = create_engine(db_url)
    db = create_sessionmaker(engine)
    ctx["engine"] = engine
    ctx["db"] = db
    
    graph_repo = Neo4jGraphBuilder(config.NEO4J_URI, config.NEO4J_USER, config.NEO4J_PASSWORD)
    await graph_repo.connect()
    ctx["graph_repo"] = graph_repo


async def shutdown(ctx: dict) -> None:
    graph_repo = ctx.get("graph_repo")
    if graph_repo is not None:
        await graph_repo.disconnect()
        
    engine = ctx.get("engine")
    if engine is not None:
        await engine.dispose()

class FlowsWorkerSettings:
    redis_settings = _redis_settings_from_url(config.REDIS_URL or "redis://localhost:6379/0")
    queue_name = "flows_queue"
    functions = [run_find_all_flows]
    on_startup = startup
    on_shutdown = shutdown
    job_serializer = arq_job_serializer
    job_deserializer = arq_job_deserializer

if __name__ == "__main__":
    run_worker(FlowsWorkerSettings)