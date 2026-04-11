import os
import asyncio
import logging
import uuid

from src.config import config
from src.graph.builder import Neo4jGraphBuilder
from src.crawler.session import CrawlSession

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = "https://the-internet.herokuapp.com/add_remove_elements/"
QUOTES = "https://quotes.toscrape.com/"
OTHER_URL = "https://en.wikipedia.org/wiki/Main_Page"
X = "https://the-internet.herokuapp.com/add_remove_elements/"

async def main():
    logger.info("Starting CoverIt Crawler...")
    logger.info("Connecting to Neo4j...")
    graph_builder = Neo4jGraphBuilder(
        config.NEO4J_URI, config.NEO4J_USER, config.NEO4J_PASSWORD
    )
    await graph_builder.connect()

    try:
        crawl_session_id = str(uuid.uuid4())
        config_path = os.path.join(os.path.dirname(__file__), "input_defaults.json") 
        session = CrawlSession(
            base_url=BASE_URL,
            graph_builder=graph_builder,
            config_path = config_path,
            session_id = crawl_session_id,
            headless=False,  
        )

        logger.info("Starting crawl...")
        await session.run_crawl(max_states=20, max_transitions=200)

        logger.info("\nCrawler execution successful!")

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)

    finally:
        logger.info("Cleaning up...")
        await graph_builder.disconnect()
        logger.info("Done!")


if __name__ == "__main__":
    asyncio.run(main())
