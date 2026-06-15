from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base
from src.db.enums import CrawlStatus, crawl_status_enum
from src.db.schemas.target_application_version import TargetApplicationVersion


class CrawlSession(Base):
    __tablename__ = "crawl_sessions"

    crawl_session_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)

    app_version_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("target_application_versions.id"),
    )

    status: Mapped[CrawlStatus | None] = mapped_column(crawl_status_enum)

    config: Mapped[dict[str, Any] | Any | None] = mapped_column(JSON)

    state_count: Mapped[int | None] = mapped_column(Integer)
    transition_count: Mapped[int | None] = mapped_column(Integer)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    error: Mapped[str | None] = mapped_column(String)

    app_version: Mapped[TargetApplicationVersion | None] = relationship(
        TargetApplicationVersion,
        lazy="joined",
    )
