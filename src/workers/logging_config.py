from __future__ import annotations

import logging
import os

LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


class DropNeo4jNotificationFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not str(record.getMessage()).startswith(
            "Received notification from DBMS server"
        )


def worker_log_level_name() -> str:
    value = os.getenv("CRAWLER_LOG_LEVEL") or os.getenv("LOG_LEVEL") or "INFO"
    value = value.strip().upper()
    if not value:
        return "INFO"
    if isinstance(logging.getLevelName(value), int):
        return value
    return "INFO"


def configure_worker_logging(worker_name: str) -> None:
    level_name = worker_log_level_name()
    level = logging.getLevelName(level_name)
    logging.basicConfig(level=level, format=LOG_FORMAT, force=True)
    logging.getLogger().setLevel(level)

    notification_filter = DropNeo4jNotificationFilter()
    logging.getLogger().addFilter(notification_filter)
    logging.getLogger("neo4j").addFilter(notification_filter)
    logging.getLogger("neo4j.notifications").addFilter(notification_filter)
    logging.getLogger("neo4j").setLevel(logging.WARNING)
    logging.getLogger("neo4j.notifications").setLevel(logging.WARNING)
    logging.getLogger("neo4j.notifications").disabled = True
    logging.getLogger("neo4j.notifications").propagate = False

    logging.getLogger(__name__).info(
        "Configured crawler worker logging worker=%s level=%s",
        worker_name,
        level_name,
    )
