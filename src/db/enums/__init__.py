from sqlalchemy import Enum as SAEnum

from src.db.enums.crawl_status import CrawlStatus
from src.db.enums.test_flow_type import TestFlowType

crawl_status_enum = SAEnum(
    CrawlStatus,
    name="CrawlStatus",
    create_type=False,
)

test_flow_type_enum = SAEnum(
    TestFlowType,
    name="TestFlowType",
    create_type=False,
)
