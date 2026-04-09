import asyncio
import logging

from src.config import config
from src.db.connection import DatabaseConnection
from src.db.repository import Repository
from src.models.domain import Project, TargetApplication, ApplicationVersion, CrawlSession
from src.graph.builder import Neo4jGraphBuilder
from src.crawler.session import CrawlSessionManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = "https://quotes.toscrape.com/"
OTHER_URL = "https://en.wikipedia.org/wiki/Main_Page"
X = "https://the-internet.herokuapp.com/add_remove_elements/"

async def main():
    logger.info("Starting CoverIt Crawler...")

    logger.info("Connecting to PostgreSQL...")
    db_conn = DatabaseConnection(config.pg_connection_string)
    await db_conn.connect()

    logger.info("Connecting to Neo4j...")
    graph_builder = Neo4jGraphBuilder(
        config.NEO4J_URI, config.NEO4J_USER, config.NEO4J_PASSWORD
    )
    await graph_builder.connect()

    try:
        async with db_conn.session_factory() as session:
            repo = Repository(session)

            logger.info("Creating project...")
            project = Project(
                name="Example Application",
                description="An example web application for crawling",
            )
            project_id = await repo.projects.create(project)
            logger.info(f"Created project: {project_id}")

            logger.info("Creating target application...")
            target_app = TargetApplication(
                project_id=project_id,
                name="Example Web App",
                base_url=BASE_URL,
                auth_type=None,
            )
            app_id = await repo.applications.create(target_app)
            logger.info(f"Created target application: {app_id}")

            logger.info("Creating application version...")
            app_version = ApplicationVersion(
                project_id=project_id,
                app_id=app_id,
                version_label="1.0.0",
                environment="dev",
                commit_hash="abc123def456",
            )
            app_version_id = await repo.application_versions.create(app_version)
            logger.info(f"Created application version: {app_version_id}")

            await repo.commit()

            logger.info("Creating crawl session...")
            crawl_session = CrawlSession(
                app_version_id=app_version_id,
                trigger_type="manual",
                status="PENDING",
            )

            manager = CrawlSessionManager(
                session=crawl_session,
                app_version_id=app_version_id,
                base_url=BASE_URL,
                repository=repo,
                graph_builder=graph_builder,
                headless=False,  
            )

            logger.info(f"Created crawl session: {crawl_session.crawl_session_id}")

            logger.info("Starting crawl...")
            await manager.run_crawl(max_states=20, max_transitions=200)

            logger.info("\nCrawler execution successful!")

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)

    finally:
        logger.info("Cleaning up...")
        await graph_builder.disconnect()
        await db_conn.disconnect()
        logger.info("Done!")


if __name__ == "__main__":
    asyncio.run(main())
