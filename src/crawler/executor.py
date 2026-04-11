import re
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from ..browser.engine import BrowserEngine
from ..config import Config, config
from ..models.graph import AbstractTransition, CrawlAction


@dataclass
class StateReplayInfo:
    checkpoint_url: str
    actions: List[CrawlAction] = field(default_factory=list)

class InputValueResolver:
    def __init__(
        self, 
        config_path: Optional[str] = None, 
    ):
        self._config = self._load_config(config_path)

    def _load_config(self, path: Optional[str]) -> Dict[str, Any]:
        if not path:
            return {"field_patterns": {}, "type_fallbacks": {}}
        
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def resolve(self, element: dict) -> str:
        hint_keys = [
            element.get("id", ""),
            element.get("name", ""),
            element.get("placeholder", ""),
            element.get("label", ""),
        ]

        patterns = self._config.get("field_patterns", {})
        best_value: Optional[str] = None
        best_len = -1
        for key in hint_keys:
            if not key:
                continue
            normalized = re.sub(r"[\s_\-]", "", str(key).lower())
            for pattern, value in patterns.items():
                if pattern and pattern in normalized:
                    if len(pattern) > best_len:
                        best_value = str(value)
                        best_len = len(pattern)

        if best_value is not None:
            return self._apply_constraints(best_value, element)

        fallbacks = self._config.get("type_fallbacks", {})
        fallback = str(fallbacks.get(element.get("type", "text"), "test"))
        return self._apply_constraints(fallback, element)

    def _apply_constraints(self, value: str, element: dict) -> str:
        t = str(element.get("type", "") or "").lower()
        maxlength = element.get("maxlength")
        if maxlength is not None:
            try:
                ml = int(maxlength)
                if ml >= 0:
                    value = value[:ml]
            except Exception:
                pass

        if t in ("number", "range"):
            chosen = None
            min_v = element.get("min")
            max_v = element.get("max")
            try:
                if min_v is not None:
                    chosen = str(int(float(min_v)))
            except Exception:
                chosen = None
            if chosen is None:
                try:
                    if max_v is not None:
                        chosen = str(int(float(max_v)))
                except Exception:
                    chosen = None
            if chosen is not None:
                value = chosen

        return value

class EventExecutor:
    def __init__(self, browser: BrowserEngine, config_path: Optional[str] = None):
        self._browser = browser
        self._resolver = InputValueResolver(config_path=config_path)
        self._transition_log: List[AbstractTransition] = []

    def resolve_value(self, element: dict) -> str:
        return self._resolver.resolve(element)

    async def execute_action(self, action: CrawlAction) -> None:
        try:
            frame_url = None
            frame_name = None
            if action.metadata:
                frame = action.metadata.get("frame")
                if isinstance(frame, dict):
                    frame_url = frame.get("url") or frame.get("src")
                    frame_name = frame.get("name")

            match action.action_type:
                case "click":
                    await self._browser.click(action.selector, frame_url=frame_url, frame_name=frame_name)
                case "type":
                    await self._browser.type_text(action.selector, action.value, frame_url=frame_url, frame_name=frame_name)
                case "select":
                    await self._browser.select_option(action.selector, action.value, frame_url=frame_url, frame_name=frame_name)
                case "navigate":
                    await self._browser.navigate(action.value)
                case "press":
                    await self._browser.press_key(action.selector, action.value, frame_url=frame_url, frame_name=frame_name)
                case _:
                    raise ValueError(f"Unknown action type: {action.action_type}")
        except Exception as e:
            target = action.selector or action.value
            raise RuntimeError(
                f"Failed to execute {action.action_type} on {target}: {e}"
            ) from e

    def plan_form_submission(
        self,
        form: dict,
        *,
        overrides: Optional[Dict[str, str]] = None,
    ) -> Optional[List[CrawlAction]]:
        fields = list(form.get("fields", []))
        submit = form.get("submit")
        if not submit or not submit.get("selector"):
            return None

        actions: List[CrawlAction] = []

        radio_groups: Dict[str, List[dict]] = {}
        for field_el in fields:
            field_type = str(field_el.get("type", "") or "").lower()
            if field_type == "radio":
                key = str(field_el.get("name") or field_el.get("id") or "radio")
                radio_groups.setdefault(key, []).append(field_el)

        chosen_radios: List[dict] = []
        for group_fields in radio_groups.values():
            if any(bool(f.get("checked")) for f in group_fields):
                continue
            chosen_radios.append(group_fields[0])

        for field_el in fields:
            tag = str(field_el.get("tag", "") or "").lower()
            field_type = str(field_el.get("type", "") or "").lower()
            selector = str(field_el.get("selector", "") or "")
            frame = field_el.get("frame") or form.get("frame")

            if not selector:
                continue
            if field_type in ("submit", "button", "reset", "hidden", "image", "file"):
                continue
            if field_el.get("disabled") or field_el.get("readonly"):
                continue

            if tag == "select":
                options = [o for o in field_el.get("options", []) if o.get("value")]
                if options:
                    value = str(options[0]["value"])
                    actions.append(
                        CrawlAction(
                            action_type="select",
                            selector=selector,
                            value=value,
                            description=f"Select '{options[0].get('text', value)}'",
                            metadata={
                                "form_id": form.get("form_id"),
                                "field": field_el.get("name") or field_el.get("id"),
                                "frame": frame,
                            },
                        )
                    )

            elif field_type == "checkbox":
                required = bool(field_el.get("required"))
                checked = bool(field_el.get("checked"))
                if required and not checked:
                    actions.append(
                        CrawlAction(
                            action_type="click",
                            selector=selector,
                            description="Check required checkbox",
                            metadata={
                                "form_id": form.get("form_id"),
                                "field": field_el.get("name") or field_el.get("id"),
                                "frame": frame,
                            },
                        )
                    )

            elif field_type == "radio":
                if field_el in chosen_radios:
                    actions.append(
                        CrawlAction(
                            action_type="click",
                            selector=selector,
                            description="Select radio option",
                            metadata={
                                "form_id": form.get("form_id"),
                                "field": field_el.get("name") or field_el.get("id"),
                                "frame": frame,
                            },
                        )
                    )

            elif tag in ("input", "textarea"):
                value: Optional[str] = None
                if overrides:
                    if field_type == "password" and overrides.get("password"):
                        value = overrides["password"]
                    elif field_type in ("text", "email", "search", "tel", "url") and overrides.get("username"):
                        label = str(field_el.get("label", "") or "").lower()
                        name = str(field_el.get("name", "") or "").lower()
                        placeholder = str(field_el.get("placeholder", "") or "").lower()
                        if any(k in (label + " " + name + " " + placeholder) for k in ("user", "email", "login")):
                            value = overrides["username"]

                if value is None:
                    value = self._resolver.resolve(field_el)

                actions.append(
                    CrawlAction(
                        action_type="type",
                        selector=selector,
                        value=value,
                        description="Type input",
                        metadata={
                            "form_id": form.get("form_id"),
                            "field": field_el.get("name") or field_el.get("id"),
                            "type": field_type,
                            "frame": frame,
                        },
                    )
                )

        method = str(form.get("method", "get") or "get").lower()
        submit_frame = submit.get("frame") if isinstance(submit, dict) else None
        actions.append(
            CrawlAction(
                action_type="click",
                selector=str(submit["selector"]),
                description=f"Submit form '{form.get('form_id', '')}'",
                metadata={
                    "form_id": form.get("form_id"),
                    "form_method": method,
                    "form_action": form.get("action", ""),
                    "frame": submit_frame or form.get("frame"),
                },
            )
        )

        return actions

    def log_transition(self, transition: AbstractTransition) -> None:
        self._transition_log.append(transition)

    def get_transition_log(self) -> List[AbstractTransition]:
        return self._transition_log


class StateReplayer:
    def __init__(self, browser: BrowserEngine, executor: EventExecutor, settings: Config = config):
        self._browser = browser
        self._executor = executor
        self._settings = settings
        self._replay_map: Dict[str, StateReplayInfo] = {}

    def register(self, state_hash: str, info: StateReplayInfo) -> None:
        self._replay_map[state_hash] = info

    def get_info(self, state_hash: str) -> Optional[StateReplayInfo]:
        return self._replay_map.get(state_hash)

    async def replay_to(self, state_hash: str) -> bool:
        info = self._replay_map.get(state_hash)
        if not info:
            return False

        last_error: Optional[Exception] = None
        for _ in range(self._settings.REPLAY_RETRY_COUNT + 1):
            try:
                await self._browser.navigate(info.checkpoint_url)
                await self._browser.wait_for_settle()
                for action in info.actions:
                    await self._executor.execute_action(action)
                await self._browser.wait_for_settle()
                current_hash = await self._browser.get_state_hash()
                if current_hash == state_hash:
                    return True
            except Exception as e:
                last_error = e

        if last_error:
            raise last_error
        return False