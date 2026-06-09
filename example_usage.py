import os
import asyncio
import logging
import uuid

from src.config import config
from src.graph import create_graph
from src.crawler.session import CrawlSession

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = "https://tryscrapeme.com/"
QUOTES = "https://quotes.toscrape.com/"
OTHER_URL = "https://en.wikipedia.org/wiki/Main_Page"
X = "https://the-internet.herokuapp.com/challenging_dom"

async def main():
    logger.info("Starting CoverIt Crawler...")
    logger.info("Connecting to Neo4j...")
    client, graph = await create_graph(
        config.NEO4J_URI,
        config.NEO4J_USER,
        config.NEO4J_PASSWORD,
    )

    try:
        crawl_session_id = str(uuid.uuid4())
        config_path = os.path.join(os.path.dirname(__file__), "src", "configs", "input_defaults.json")
        session = CrawlSession(
            base_url=BASE_URL,
            graph_builder=graph,
            config_path=config_path,
            session_id=crawl_session_id,
            headless=False,
        )

        logger.info("Starting crawl...")
        await session.run_crawl()

        logger.info("\nCrawler execution successful!")

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)

    finally:
        logger.info("Cleaning up...")
        await client.close()
        logger.info("Done!")


if __name__ == "__main__":
    asyncio.run(main())
