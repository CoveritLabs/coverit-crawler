from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Column, String, Text, DateTime, Boolean, Integer, Float, JSON, ForeignKey, Uuid
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Mapped, relationship

Base = declarative_base()


class Project(Base):
    __tablename__ = "projects"

    project_id = Column(Uuid, primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.now(timezone.utc))

    target_applications: Mapped[list["TargetApplication"]] = relationship(
        "TargetApplication", back_populates="project", cascade="all, delete-orphan"
    )


class TargetApplication(Base):
    __tablename__ = "target_applications"

    app_id = Column(Uuid, primary_key=True, default=uuid4)
    project_id = Column(Uuid, ForeignKey("projects.project_id"), nullable=False)
    name = Column(String(255), nullable=False)
    base_url = Column(String(2048), nullable=False)
    auth_type = Column(String(50), nullable=True)
    config_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.now(timezone.utc))

    project = relationship("Project", back_populates="target_applications")
    application_versions: Mapped[list["ApplicationVersion"]] = relationship(
        "ApplicationVersion", back_populates="target_application", cascade="all, delete-orphan"
    )


class ApplicationVersion(Base):
    __tablename__ = "application_versions"

    app_version_id = Column(Uuid, primary_key=True, default=uuid4)
    app_id = Column(Uuid, ForeignKey("target_applications.app_id"), nullable=False)
    project_id = Column(Uuid, ForeignKey("projects.project_id"), nullable=False)
    version_label = Column(String(255), nullable=False)
    environment = Column(String(50), nullable=False, default="dev")
    commit_hash = Column(String(128), nullable=True)
    captured_at = Column(DateTime(timezone=True), nullable=False, default=datetime.now(timezone.utc))

    target_application = relationship("TargetApplication", back_populates="application_versions")
    crawl_sessions: Mapped[list["CrawlSession"]] = relationship(
        "CrawlSession", back_populates="application_version", cascade="all, delete-orphan"
    )
    locators: Mapped[list["Locator"]] = relationship(
        "Locator", back_populates="application_version", cascade="all, delete-orphan"
    )


class CrawlSession(Base):
    __tablename__ = "crawl_sessions"

    crawl_session_id = Column(Uuid, primary_key=True, default=uuid4)
    app_version_id = Column(Uuid, ForeignKey("application_versions.app_version_id"), nullable=False)
    trigger_type = Column(String(50), nullable=False, default="manual")
    status = Column(String(50), nullable=False, default="PENDING")
    state_count = Column(Integer, nullable=False, default=0)
    transition_count = Column(Integer, nullable=False, default=0)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    application_version = relationship("ApplicationVersion", back_populates="crawl_sessions")


class Locator(Base):
    __tablename__ = "locators"

    locator_id = Column(Uuid, primary_key=True, default=uuid4)
    app_version_id = Column(Uuid, ForeignKey("application_versions.app_version_id"), nullable=False)
    locator_ref = Column(String(255), nullable=False)
    element_name = Column(String(255), nullable=False)
    semantic_role = Column(String(100), nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.now(timezone.utc))

    application_version = relationship("ApplicationVersion", back_populates="locators")
    locator_versions: Mapped[list["LocatorVersion"]] = relationship(
        "LocatorVersion", back_populates="locator", cascade="all, delete-orphan"
    )


class LocatorVersion(Base):
    __tablename__ = "locator_versions"

    locator_version_id = Column(Uuid, primary_key=True, default=uuid4)
    locator_id = Column(Uuid, ForeignKey("locators.locator_id"), nullable=False)
    locator_strategy = Column(String(100), nullable=False)
    locator_value = Column(String(2048), nullable=False)
    confidence_score = Column(Float, nullable=False, default=1.0)
    source_type = Column(String(50), nullable=False)
    is_current = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.now(timezone.utc))

    locator = relationship("Locator", back_populates="locator_versions")

