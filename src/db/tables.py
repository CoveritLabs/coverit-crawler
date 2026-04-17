from sqlalchemy import JSON, Column, DateTime, Integer, MetaData, String, Table
from sqlalchemy.dialects.postgresql import ENUM, UUID


metadata = MetaData()


crawl_status_enum = ENUM(
    "UNSPECIFIED",
    "QUEUED",
    "RUNNING",
    "COMPLETED",
    "FAILED",
    "ABORTED",
    "PAUSED",
    "NEW",
    name="CrawlStatus",
    create_type=False,
)


crawl_sessions = Table(
    "crawl_sessions",
    metadata,
    Column("crawl_session_id", UUID(as_uuid=False), primary_key=True),
    Column("app_version_id", UUID(as_uuid=False)),
    Column("status", crawl_status_enum),
    Column("config", JSON),
    Column("state_count", Integer),
    Column("transition_count", Integer),
    Column("started_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    Column("error", String),
)


target_application_versions = Table(
    "target_application_versions",
    metadata,
    Column("id", UUID(as_uuid=False), primary_key=True),
    Column("target_application_id", UUID(as_uuid=False)),
)


target_applications = Table(
    "target_applications",
    metadata,
    Column("id", UUID(as_uuid=False), primary_key=True),
    Column("base_url", String),
)
