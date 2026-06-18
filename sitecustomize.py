import logging

logging.getLogger("neo4j").setLevel(logging.WARNING)
logging.getLogger("neo4j.notifications").setLevel(logging.WARNING)
logging.getLogger("neo4j.notifications").disabled = True
logging.getLogger("neo4j.notifications").propagate = False
