import re
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from ..browser.engine import BrowserEngine
from ..config import Config, config
from ..models.graph import AbstractTransition, CrawlAction
from .element_hints import element_display_hint
from .serialization import stable_json_dumps


@dataclass
class StateReplayInfo:
    checkpoint_url: str
    checkpoint_state_hash: str = ""
    checkpoint_kind: str = "url_change"
    actions: List[CrawlAction] = field(default_factory=list)
    fallback_checkpoint_url: Optional[str] = None
    fallback_checkpoint_state_hash: Optional[str] = None
    fallback_actions: List[CrawlAction] = field(default_factory=list)

    def to_neo4j_props(self, *, state_hash: str) -> Dict[str, Any]:
        def action_to_dict(action: CrawlAction) -> Dict[str, Any]:
            return {
                "id": action.action_id,
                "type": action.action_type,
                "selector": action.selector,
                "value": action.value,
                "description": action.description,
                "metadata": action.metadata,
            }

        props: Dict[str, Any] = {
            "replay_recipe_version": 1,
            "checkpoint_url": self.checkpoint_url,
            "checkpoint_state_hash": self.checkpoint_state_hash,
            "checkpoint_kind": self.checkpoint_kind,
            "replay_actions_json": stable_json_dumps([action_to_dict(a) for a in self.actions]),
        }

        if self.fallback_checkpoint_url:
            props["fallback_checkpoint_url"] = self.fallback_checkpoint_url
        if self.fallback_checkpoint_state_hash:
            props["fallback_checkpoint_state_hash"] = self.fallback_checkpoint_state_hash
        if self.fallback_actions:
            props["fallback_actions_json"] = stable_json_dumps([action_to_dict(a) for a in self.fallback_actions])

        props["is_checkpoint"] = bool(state_hash and self.checkpoint_state_hash == state_hash)
        return props

    def score_for_state(self, state_hash: str) -> tuple[int, int, int, int, str]:
        is_self_checkpoint = bool(state_hash and self.checkpoint_state_hash == state_hash)
        kind_rank = 0 if self.checkpoint_kind == "initial" else 1
        checkpoint_url = str(self.checkpoint_url or "")
        return (
            0 if is_self_checkpoint else 1,
            len(self.actions),
            len(self.fallback_actions),
            kind_rank,
            checkpoint_url,
        )

class InputValueResolver:
    def __init__(
        self,
        config_path: Optional[str] = None,
        input_defaults: Optional[Dict[str, Any]] = None,
    ):
        self._config = input_defaults if isinstance(input_defaults, dict) else self._load_config(config_path)

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
    def __init__(
        self,
        browser: BrowserEngine,
        config_path: Optional[str] = None,
        input_defaults: Optional[Dict[str, Any]] = None,
    ):
        self._browser = browser
        self._resolver = InputValueResolver(config_path=config_path, input_defaults=input_defaults)
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
    ) -> Optional[List[CrawlAction]]:
        fields = list(form.get("fields", []))
        submit = form.get("submit")
        if not submit or not submit.get("selector"):
            return None

        actions: List[CrawlAction] = []

        form_id = str(form.get("form_id", "") or "").strip()
        form_method = str(form.get("method", "get") or "get").lower()
        form_action = str(form.get("action", "") or "").strip()

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
                    label_hint = element_display_hint(field_el, label_keys=("label", "aria_label"))
                    option_text = str(options[0].get("text", value) or value).strip()
                    actions.append(
                        CrawlAction(
                            action_type="select",
                            selector=selector,
                            value=value,
                            description=f"Select '{option_text}' for {label_hint or 'select'}",
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
                    label_hint = element_display_hint(field_el, label_keys=("label", "aria_label"))
                    actions.append(
                        CrawlAction(
                            action_type="click",
                            selector=selector,
                            description=f"Check required checkbox {label_hint}".strip(),
                            metadata={
                                "form_id": form.get("form_id"),
                                "field": field_el.get("name") or field_el.get("id"),
                                "frame": frame,
                            },
                        )
                    )

            elif field_type == "radio":
                if field_el in chosen_radios:
                    label_hint = element_display_hint(field_el, label_keys=("label", "aria_label"))
                    actions.append(
                        CrawlAction(
                            action_type="click",
                            selector=selector,
                            description=f"Select radio option {label_hint}".strip(),
                            metadata={
                                "form_id": form.get("form_id"),
                                "field": field_el.get("name") or field_el.get("id"),
                                "frame": frame,
                            },
                        )
                    )

            elif tag in ("input", "textarea"):
                value = self._resolver.resolve(field_el)

                label_hint = element_display_hint(field_el, label_keys=("label", "aria_label"))
                type_hint = field_type or tag
                desc = f"Type into {type_hint} {label_hint}".strip()

                actions.append(
                    CrawlAction(
                        action_type="type",
                        selector=selector,
                        value=value,
                        description=desc,
                        metadata={
                            "form_id": form.get("form_id"),
                            "field": field_el.get("name") or field_el.get("id"),
                            "type": field_type,
                            "frame": frame,
                        },
                    )
                )

        submit_frame = submit.get("frame") if isinstance(submit, dict) else None
        submit_label = element_display_hint(submit, label_keys=("label", "aria_label")) if isinstance(submit, dict) else ""
        submit_desc_parts = []
        if form_id:
            submit_desc_parts.append(f"Submit form '{form_id}'")
        else:
            submit_desc_parts.append("Submit form")
        submit_desc_parts.append(form_method.upper())
        if form_action:
            submit_desc_parts.append(form_action)
        if submit_label:
            submit_desc_parts.append(f"via {submit_label}")

        actions.append(
            CrawlAction(
                action_type="click",
                selector=str(submit["selector"]),
                description=" ".join(submit_desc_parts).strip(),
                metadata={
                    "form_id": form.get("form_id"),
                    "form_method": form_method,
                    "form_action": form_action,
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

    def register(self, state_hash: str, info: StateReplayInfo) -> bool:
        existing = self._replay_map.get(state_hash)
        if existing is None:
            self._replay_map[state_hash] = info
            return True

        if info.score_for_state(state_hash) < existing.score_for_state(state_hash):
            self._replay_map[state_hash] = info
            return True

        return False

    def get_info(self, state_hash: str) -> Optional[StateReplayInfo]:
        return self._replay_map.get(state_hash)

    async def replay_to(self, state_hash: str) -> bool:
        info = self._replay_map.get(state_hash)
        if not info:
            return False

        async def attempt(checkpoint_url: str, actions: List[CrawlAction]) -> bool:
            last_error: Optional[Exception] = None
            for _ in range(self._settings.REPLAY_RETRY_COUNT + 1):
                try:
                    await self._browser.navigate(checkpoint_url)
                    await self._browser.wait_for_settle()
                    for action in actions:
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

        try:
            if await attempt(info.checkpoint_url, info.actions):
                return True
        except Exception:
            pass

        if info.fallback_checkpoint_url:
            return await attempt(info.fallback_checkpoint_url, info.fallback_actions)
        return False