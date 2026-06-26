from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

__all__ = [
    "Base",
    "CrawlSession",
    "CrawlStatus",
    "TargetApplication",
    "TargetApplicationVersion",
    "crawl_status_enum",
    "create_engine",
    "create_sessionmaker",
    "fetch_job_inputs",
    "fetch_graph_id",
    "get_session_status",
    "mark_aborted_if_active",
    "mark_completed_if_running",
    "mark_failed_if_running",
    "mark_finished_at_if_aborted",
    "mark_queued_running",
    "update_counts_if_active",
    "TestFlow",
    "create_test_flow",
    "fetch_test_flow_details",
]

_EXPORTS: dict[str, tuple[str, str]] = {
    "Base": ("src.db.base", "Base"),
    "CrawlSession": ("src.db.schemas.crawl_sessions", "CrawlSession"),
    "CrawlStatus": ("src.db.enums.crawl_status", "CrawlStatus"),
    "TargetApplication": ("src.db.schemas.target_application", "TargetApplication"),
    "TargetApplicationVersion": ("src.db.schemas.target_application_version", "TargetApplicationVersion"),
    "crawl_status_enum": ("src.db.enums", "crawl_status_enum"),
    "create_engine": ("src.db.database", "create_engine"),
    "create_sessionmaker": ("src.db.database", "create_sessionmaker"),
    "fetch_job_inputs": ("src.db.repositories.crawl_sessions", "fetch_job_inputs"),
    "fetch_graph_id": ("src.db.repositories.crawl_sessions", "fetch_graph_id"),
    "get_session_status": ("src.db.repositories.crawl_sessions", "get_session_status"),
    "mark_completed_if_running": ("src.db.repositories.crawl_sessions", "mark_completed_if_running"),
    "mark_failed_if_running": ("src.db.repositories.crawl_sessions", "mark_failed_if_running"),
    "mark_aborted_if_active": ("src.db.repositories.crawl_sessions", "mark_aborted_if_active"),
    "mark_finished_at_if_aborted": ("src.db.repositories.crawl_sessions", "mark_finished_at_if_aborted"),
    "mark_queued_running": ("src.db.repositories.crawl_sessions", "mark_queued_running"),
    "update_counts_if_active": ("src.db.repositories.crawl_sessions", "update_counts_if_active"),
    "TestFlow": ("src.db.schemas.test_flow", "TestFlow"),
    "create_test_flow": ("src.db.repositories.test_flows", "create_test_flow"),
    "fetch_test_flow_details": ("src.db.repositories.test_flows", "fetch_test_flow_details"),
}


def __getattr__(name: str) -> Any:
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr = target
    value = getattr(import_module(module_name), attr)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals().keys()) | set(_EXPORTS.keys()))


if TYPE_CHECKING:
    from src.db.base import Base
    from src.db.database import create_engine, create_sessionmaker
    from src.db.enums import crawl_status_enum
    from src.db.enums.crawl_status import CrawlStatus
    from src.db.repositories.crawl_sessions import (
        fetch_graph_id,
        fetch_job_inputs,
        get_session_status,
        mark_completed_if_running,
        mark_failed_if_running,
        mark_aborted_if_active,
        mark_finished_at_if_aborted,
        mark_queued_running,
        update_counts_if_active,
    )
    from src.db.schemas.crawl_sessions import CrawlSession
    from src.db.schemas.target_application import TargetApplication
    from src.db.schemas.target_application_version import TargetApplicationVersion
    from src.db.schemas.test_flow import TestFlow
    from src.db.repositories.test_flows import (create_test_flow, fetch_test_flow_details)
