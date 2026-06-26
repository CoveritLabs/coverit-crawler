import asyncio
import logging
import os
import uuid

from src.config import config
from src.crawler.session import CrawlSession
from src.graph import create_graph


class _DropNeo4jNotificationFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not str(record.getMessage()).startswith("Received notification from DBMS server")


_neo4j_notification_filter = _DropNeo4jNotificationFilter()
logging.getLogger().addFilter(_neo4j_notification_filter)
logging.getLogger("neo4j").addFilter(_neo4j_notification_filter)
logging.getLogger("neo4j.notifications").addFilter(_neo4j_notification_filter)
logging.getLogger("neo4j").setLevel(logging.ERROR)
logging.getLogger("neo4j.notifications").disabled = True
logging.getLogger("neo4j.notifications").propagate = False
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = "https://www.saucedemo.com/"
QUOTES = "https://quotes.toscrape.com/"
BOOKS = "https://books.toscrape.com/"
OTHER_URL = "https://en.wikipedia.org/wiki/Main_Page"
X = "https://the-internet.herokuapp.com/challenging_dom"
WEBSITE_1 = "file:///D:/crawler_test_website/nexus_commerce/index.html"


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
            headless=config.HEADLESS,
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
