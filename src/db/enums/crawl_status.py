from enum import Enum


class CrawlStatus(str, Enum):
    UNSPECIFIED = "UNSPECIFIED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"
    PAUSED = "PAUSED"
    NEW = "NEW"
