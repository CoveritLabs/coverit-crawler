from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base
from src.db.schemas.crawl_sessions import CrawlSession
from src.db.schemas.target_application_version import TargetApplicationVersion
from src.db.enums import TestFlowType, test_flow_type_enum

class TestFlow(Base):
    __tablename__ = "test_flows"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)

    crawl_session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("crawl_sessions.crawl_session_id", ondelete="CASCADE"),
        index=True,
    )

    app_version_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("target_application_versions.id", ondelete="CASCADE"),
        index=True,
    )

    checkpoint_state_hash: Mapped[str] = mapped_column(String)

    transition_refs: Mapped[list[str]] = mapped_column(ARRAY(String))

    test_flow_type: Mapped[TestFlowType] = mapped_column(test_flow_type_enum)

    step_count: Mapped[int] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    modified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    crawl_session: Mapped[CrawlSession] = relationship(
        CrawlSession, lazy="joined"
    )
    app_version: Mapped[TargetApplicationVersion] = relationship(
        TargetApplicationVersion, lazy="joined"
    )
