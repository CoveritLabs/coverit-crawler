from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.config import Config
from src.utils.coercion import coerce_bool, coerce_int, coerce_str


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_input_config_path() -> str | None:
    candidate = _repo_root() / "src" / "configs" / "input_defaults.json"
    return str(candidate) if candidate.exists() else None


@dataclass(frozen=True)
class CrawlJob:
    base_url: str
    session_id: str
    headless: bool
    timeout_ms: int
    max_states: int
    max_transitions: int
    max_elements_per_state: int
    max_select_options_per_element: int
    max_action_repeats_per_url: int
    action_retry_count: int
    replay_retry_count: int
    popup_timeout_ms: int
    dom_quiet_ms: int
    dom_settle_timeout_ms: int
    use_dom_quiescence: bool
    page_load_state: str
    click_non_http_links: bool
    defer_destructive_actions: bool
    destructive_keywords: str
    input_defaults: dict[str, Any] | None = None
    input_defaults_path: str | None = None

    @staticmethod
    def from_dict(payload: dict[str, Any], settings: Config) -> CrawlJob:
        nested_settings = payload.get("settings")
        if not isinstance(nested_settings, dict):
            raise ValueError("settings must be an object")

        base_url = str(payload.get("base_url") or "").strip()
        if not base_url:
            raise ValueError("base_url is required")

        session_id = str(payload.get("session_id") or "").strip() or str(uuid4())
        headless = coerce_bool(nested_settings.get("headless"), bool(getattr(settings, "HEADLESS", True)))
        timeout_ms = coerce_int(nested_settings.get("timeout_ms"), int(getattr(settings, "TIMEOUT_MS", 3000)))
        max_states = coerce_int(nested_settings.get("max_states"), int(getattr(settings, "MAX_STATES", 1000)))
        max_transitions = coerce_int(
            nested_settings.get("max_transitions"),
            int(getattr(settings, "MAX_TRANSITIONS", 5000)),
        )
        max_elements_per_state = coerce_int(
            nested_settings.get("max_elements_per_state"),
            int(getattr(settings, "MAX_ELEMENTS_PER_STATE", 30)),
        )
        max_select_options_per_element = coerce_int(
            nested_settings.get("max_select_options_per_element"),
            int(getattr(settings, "MAX_SELECT_OPTIONS_PER_ELEMENT", 3)),
        )
        max_action_repeats_per_url = coerce_int(
            nested_settings.get("max_action_repeats_per_url"),
            int(getattr(settings, "MAX_ACTION_REPEATS_PER_URL", 2)),
        )
        action_retry_count = coerce_int(
            nested_settings.get("action_retry_count"),
            int(getattr(settings, "ACTION_RETRY_COUNT", 1)),
        )
        replay_retry_count = coerce_int(
            nested_settings.get("replay_retry_count"),
            int(getattr(settings, "REPLAY_RETRY_COUNT", 1)),
        )
        popup_timeout_ms = coerce_int(
            nested_settings.get("popup_timeout_ms"),
            int(getattr(settings, "POPUP_TIMEOUT_MS", 3000)),
        )
        dom_quiet_ms = coerce_int(
            nested_settings.get("dom_quiet_ms"),
            int(getattr(settings, "DOM_QUIET_MS", 400)),
        )
        dom_settle_timeout_ms = coerce_int(
            nested_settings.get("dom_settle_timeout_ms"),
            int(getattr(settings, "DOM_SETTLE_TIMEOUT_MS", 3000)),
        )
        use_dom_quiescence = coerce_bool(
            nested_settings.get("use_dom_quiescence"),
            bool(getattr(settings, "USE_DOM_QUIESCENCE", True)),
        )
        page_load_state = coerce_str(
            nested_settings.get("page_load_state"),
            str(getattr(settings, "PAGE_LOAD_STATE", "networkidle")),
        )
        click_non_http_links = coerce_bool(
            nested_settings.get("click_non_http_links"),
            bool(getattr(settings, "CLICK_NON_HTTP_LINKS", False)),
        )
        defer_destructive_actions = coerce_bool(
            nested_settings.get("defer_destructive_actions"),
            bool(getattr(settings, "DEFER_DESTRUCTIVE_ACTIONS", True)),
        )
        destructive_keywords = coerce_str(
            nested_settings.get("destructive_keywords"),
            str(getattr(settings, "DESTRUCTIVE_KEYWORDS", "")),
        )
        input_defaults_path = _default_input_config_path()

        input_defaults = payload.get("input_defaults")
        if not isinstance(input_defaults, dict):
            input_defaults = None

        return CrawlJob(
            base_url=base_url,
            session_id=session_id,
            headless=headless,
            timeout_ms=timeout_ms,
            max_states=max_states,
            max_transitions=max_transitions,
            max_elements_per_state=max_elements_per_state,
            max_select_options_per_element=max_select_options_per_element,
            max_action_repeats_per_url=max_action_repeats_per_url,
            action_retry_count=action_retry_count,
            replay_retry_count=replay_retry_count,
            popup_timeout_ms=popup_timeout_ms,
            dom_quiet_ms=dom_quiet_ms,
            dom_settle_timeout_ms=dom_settle_timeout_ms,
            use_dom_quiescence=use_dom_quiescence,
            page_load_state=page_load_state,
            click_non_http_links=click_non_http_links,
            defer_destructive_actions=defer_destructive_actions,
            destructive_keywords=destructive_keywords,
            input_defaults=input_defaults,
            input_defaults_path=input_defaults_path,
        )
