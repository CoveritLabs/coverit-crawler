import re
import os
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from ..browser.engine import BrowserEngine
from ..models.graph import AbstractTransition, CrawlAction


@dataclass
class StateReplayInfo:
    checkpoint_url: str
    actions: List[CrawlAction] = field(default_factory=list)

class InputValueResolver:
    def __init__(
        self, 
        config_path: Optional[str] = None, 
        user_overrides: Optional[Dict[str, str]] = None
    ):
        self._config = self._load_config(config_path)
        
        self._user_overrides = user_overrides or {}

    def _load_config(self, path: Optional[str]) -> Dict[str, Any]:
        if not path:
            return {"field_patterns": {}, "type_fallbacks": {}}
        
        with open(os.path.join(os.path.dirname(__file__), path), 'r') as f:
            return json.load(f)

    def resolve(self, element: dict) -> str:
        hint_keys = [
            element.get("id", ""),
            element.get("name", ""),
            element.get("placeholder", ""),
            element.get("label", ""),
        ]

        for key in hint_keys:
            if key and key in self._user_overrides:
                return self._user_overrides[key]

        patterns = self._config.get("field_patterns", {})
        for key in hint_keys:
            if not key:
                continue
            normalized = re.sub(r"[\s_\-]", "", key.lower())
            for pattern, value in patterns.items():
                if pattern in normalized:
                    return value

        fallbacks = self._config.get("type_fallbacks", {})
        return fallbacks.get(element.get("type", "text"), "test")

class EventExecutor:
    def __init__(self, browser: BrowserEngine):
        self._browser = browser
        # TODO: make resolver accept qa inputs
        self._resolver = InputValueResolver(config_path="input_defaults.json")
        self._transition_log: List[AbstractTransition] = []

    async def execute_action(self, action: CrawlAction) -> None:
        try:
            match action.action_type:
                case "click":
                    await self._browser.click(action.selector)
                case "type":
                    await self._browser.type_text(action.selector, action.value)
                case "select":
                    await self._browser.select_option(action.selector, action.value)
                case "navigate":
                    await self._browser.navigate(action.value)
        except Exception as e:
            raise RuntimeError(f"Failed to execute {action.action_type} on {action.selector}: {e}") from e

    async def fill_and_submit_form(self, form: dict) -> Optional[CrawlAction]:
        for field_el in form.get("fields", []):
            tag = field_el.get("tag", "")
            field_type = field_el.get("type", "")
            selector = field_el.get("selector", "")

            if not selector or field_type in ("submit", "button", "reset", "hidden", "image"):
                continue

            if tag == "select":
                options = [o for o in field_el.get("options", []) if o.get("value")]
                if options:
                    await self.execute_action(CrawlAction(
                        action_id=f"select-{selector}",
                        action_type="select",
                        selector=selector,
                        value=options[0]["value"],
                        description=f"Select '{options[0]['value']}' in {selector}",
                    ))

            elif tag in ("input", "textarea") and field_type not in ("checkbox", "radio"):
                value = self._resolver.resolve(field_el)
                await self.execute_action(CrawlAction(
                    action_id=f"type-{selector}",
                    action_type="type",
                    selector=selector,
                    value=value,
                    description=f"Type into {selector}",
                ))

            elif field_type == "checkbox" and not field_el.get("checked"):
                await self.execute_action(CrawlAction(
                    action_id=f"check-{selector}",
                    action_type="click",
                    selector=selector,
                    description=f"Check {selector}",
                ))

        submit = form.get("submit")
        if not submit or not submit.get("selector"):
            return None

        submit_action = CrawlAction(
            action_id=f"submit-{form.get('form_id', 'form')}",
            action_type="click",
            selector=submit["selector"],
            description=f"Submit form '{form.get('form_id', '')}'",
        )
        await self.execute_action(submit_action)
        return submit_action

    def log_transition(self, transition: AbstractTransition) -> None:
        self._transition_log.append(transition)

    def get_transition_log(self) -> List[AbstractTransition]:
        return self._transition_log


class StateReplayer:
    def __init__(self, browser: BrowserEngine, executor: EventExecutor):
        self._browser = browser
        self._executor = executor
        self._replay_map: Dict[str, StateReplayInfo] = {}

    def register(self, state_id: str, info: StateReplayInfo) -> None:
        self._replay_map[state_id] = info

    def get_info(self, state_id: str) -> Optional[StateReplayInfo]:
        return self._replay_map.get(state_id)

    async def replay_to(self, state_id: str) -> None:
        info = self._replay_map.get(state_id)
        if not info:
            return
        
        await self._browser.navigate(info.checkpoint_url)
        for action in info.actions:
            await self._executor.execute_action(action)
            await self._browser.wait_for_navigation()