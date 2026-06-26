from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base
from src.db.schemas.target_application import TargetApplication


class TargetApplicationVersion(Base):
    __tablename__ = "target_application_versions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)

    target_application_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("target_applications.id"),
    )

    target_application: Mapped[TargetApplication | None] = relationship(
        TargetApplication,
        lazy="joined",
    )
