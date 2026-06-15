from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class TargetApplication(Base):
    __tablename__ = "target_applications"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    base_url: Mapped[str | None] = mapped_column(String)
