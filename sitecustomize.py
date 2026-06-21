import logging


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
