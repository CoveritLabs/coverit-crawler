import argparse
import asyncio
import logging
import os
import uuid
from src.config import config
from src.graph.factory import create_graph
from src.crawler.session.manual_crawl.manual_crawl import ManualCrawlSession

async def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Run a manual, human-guided crawl session.")
    parser.add_argument("--url", required=True, help="The starting URL")
    args = parser.parse_args()

    client, graph_builder = await create_graph(
        config.NEO4J_URI, 
        config.NEO4J_USER, 
        config.NEO4J_PASSWORD
    )
    try:
        crawl_session_id = str(uuid.uuid4())
        config_path = os.path.join(os.path.dirname(__file__), "src", "configs", "input_defaults.json")
        session = ManualCrawlSession(
            base_url=args.url,
            graph_builder=graph_builder,
            config_path=config_path,
            session_id=crawl_session_id,
            headless=False,
        )
        await session.run_crawl()
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())