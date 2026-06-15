from sqlalchemy import Enum as SAEnum

from src.db.enums.crawl_status import CrawlStatus

crawl_status_enum = SAEnum(
    CrawlStatus,
    name="CrawlStatus",
    create_type=False,
)
