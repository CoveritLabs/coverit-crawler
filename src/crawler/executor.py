from __future__ import annotations

from typing import Any

from src.browser import BrowserEngine
from src.crawler.enums import ActionType, HtmlTag, InputType
from src.crawler.input_resolver import InputValueResolver
from src.crawler.semantic_engine import SemanticEngine
from src.models import AbstractTransition, CrawlAction
from src.utils import element_display_hint


class EventExecutor:
    def __init__(
        self,
        browser: BrowserEngine,
        config_path: str | None = None,
        input_defaults: dict[str, Any] | None = None,
        semantic_engine: SemanticEngine | None = None,
    ):
        self._browser = browser
        self._resolver = InputValueResolver(
            config_path=config_path,
            input_defaults=input_defaults,
            semantic_engine=semantic_engine,
        )
        self._transition_log: list[AbstractTransition] = []

    def resolve_value(self, element: dict) -> str:
        return self._resolver.resolve(element)

    async def execute_action(self, action: CrawlAction) -> None:
        try:
            frame_url, frame_name = self._extract_frame(action.metadata)
            match action.action_type:
                case ActionType.CLICK:
                    await self._browser.click(action.selector, frame_url=frame_url, frame_name=frame_name)

                case ActionType.TYPE:
                    await self._browser.type_text(
                        action.selector,
                        action.value,
                        frame_url=frame_url,
                        frame_name=frame_name,
                    )

                case ActionType.SELECT:
                    await self._browser.select_option(
                        action.selector,
                        action.value,
                        frame_url=frame_url,
                        frame_name=frame_name,
                    )

                case ActionType.NAVIGATE:
                    await self._browser.navigate(action.value)

                case ActionType.PRESS:
                    await self._browser.press_key(
                        action.selector,
                        action.value,
                        frame_url=frame_url,
                        frame_name=frame_name,
                    )

                case _:
                    raise ValueError(f"Unknown action type: {action.action_type}")

        except Exception as e:
            target = action.selector or action.value

            raise RuntimeError(f"Failed to execute {action.action_type} on {target}: {e}") from e

    def plan_form_submission(self, form: dict) -> list[CrawlAction] | None:
        submit = form.get("submit")

        if not self._is_valid_submit(submit):
            return None

        actions: list[CrawlAction] = []
        chosen_radios = self._choose_radio_defaults(form)

        for field in form.get("fields", []):
            action = self._build_field_action(field, form, chosen_radios)

            if action:
                actions.append(action)

        actions.append(self._build_submit_action(form))

        return actions

    def log_transition(self, transition: AbstractTransition) -> None:
        self._transition_log.append(transition)

    def get_transition_log(self) -> list[AbstractTransition]:
        return self._transition_log

    def _extract_frame(self, metadata: dict | None) -> tuple[str | None, str | None]:
        if not metadata:
            return None, None

        frame = metadata.get("frame")

        if not isinstance(frame, dict):
            return None, None

        frame_url = frame.get("url") or frame.get("src")
        frame_name = frame.get("name")

        return frame_url, frame_name

    def _is_valid_submit(self, submit: dict | None) -> bool:
        return bool(submit and submit.get("selector"))

    def _choose_radio_defaults(self, form: dict) -> list[dict]:
        radio_groups: dict[str, list[dict]] = {}

        for field in form.get("fields", []):
            field_type = self._field_type(field)

            if field_type != InputType.RADIO:
                continue

            key = str(field.get("name") or field.get("id") or "radio")
            radio_groups.setdefault(key, []).append(field)

        selected: list[dict] = []

        for group_fields in radio_groups.values():
            if any(bool(field.get("checked")) for field in group_fields):
                continue

            selected.append(group_fields[0])

        return selected

    def _build_field_action(
        self,
        field: dict,
        form: dict,
        chosen_radios: list[dict],
    ) -> CrawlAction | None:
        if self._should_skip_field(field):
            return None

        tag = self._field_tag(field)
        field_type = self._field_type(field)

        if tag == HtmlTag.SELECT:
            return self._build_select_action(field, form)

        if field_type == InputType.CHECKBOX:
            return self._build_checkbox_action(field, form)

        if field_type == InputType.RADIO:
            return self._build_radio_action(field, form, chosen_radios)

        if tag in (HtmlTag.INPUT, HtmlTag.TEXTAREA):
            return self._build_text_action(field, form)

        return None

    def _build_select_action(self, field: dict, form: dict) -> CrawlAction | None:
        options = [option for option in field.get("options", []) if option.get("value")]

        if not options:
            return None

        value = str(options[0]["value"])
        option_text = str(options[0].get("text", value) or value).strip()
        label_hint = element_display_hint(field, label_keys=("label", "aria_label"))

        return CrawlAction(
            action_type=ActionType.SELECT,
            selector=str(field["selector"]),
            value=value,
            description=f"Select '{option_text}' for {label_hint or 'select'}",
            metadata=self._field_metadata(field, form),
        )

    def _build_checkbox_action(self, field: dict, form: dict) -> CrawlAction | None:
        required = bool(field.get("required"))
        checked = bool(field.get("checked"))

        if not required or checked:
            return None

        label_hint = element_display_hint(field, label_keys=("label", "aria_label"))

        return CrawlAction(
            action_type=ActionType.CLICK,
            selector=str(field["selector"]),
            description=f"Check required checkbox {label_hint}".strip(),
            metadata=self._field_metadata(field, form),
        )

    def _build_radio_action(
        self,
        field: dict,
        form: dict,
        chosen_radios: list[dict],
    ) -> CrawlAction | None:
        if field not in chosen_radios:
            return None

        label_hint = element_display_hint(field, label_keys=("label", "aria_label"))

        return CrawlAction(
            action_type=ActionType.CLICK,
            selector=str(field["selector"]),
            description=f"Select radio option {label_hint}".strip(),
            metadata=self._field_metadata(field, form),
        )

    def _build_text_action(self, field: dict, form: dict) -> CrawlAction:
        value = self._resolver.resolve(field)

        label_hint = element_display_hint(field, label_keys=("label", "aria_label"))
        type_hint = self._field_type(field) or self._field_tag(field)

        return CrawlAction(
            action_type=ActionType.TYPE,
            selector=str(field["selector"]),
            value=value,
            description=f"Type into {type_hint} {label_hint}".strip(),
            metadata={
                **self._field_metadata(field, form),
                "type": self._field_type(field),
            },
        )

    def _build_submit_action(self, form: dict) -> CrawlAction:
        submit = form["submit"]

        form_id = str(form.get("form_id", "") or "").strip()
        form_method = str(form.get("method", "get") or "get").lower()
        form_action = str(form.get("action", "") or "").strip()

        submit_label = element_display_hint(
            submit,
            label_keys=("label", "aria_label"),
        )

        description_parts = [
            f"Submit form '{form_id}'" if form_id else "Submit form",
            form_method.upper(),
        ]

        if form_action:
            description_parts.append(form_action)

        if submit_label:
            description_parts.append(f"via {submit_label}")

        return CrawlAction(
            action_type=ActionType.CLICK,
            selector=str(submit["selector"]),
            description=" ".join(description_parts).strip(),
            metadata={
                "form_id": form.get("form_id"),
                "form_method": form_method,
                "form_action": form_action,
                "frame": submit.get("frame") or form.get("frame"),
            },
        )

    def _should_skip_field(self, field: dict) -> bool:
        selector = str(field.get("selector", "") or "")

        if not selector:
            return True

        if field.get("disabled") or field.get("readonly"):
            return True

        field_type = self._field_type(field)

        return field_type in {
            InputType.SUBMIT,
            InputType.BUTTON,
            InputType.RESET,
            InputType.HIDDEN,
            InputType.IMAGE,
            InputType.FILE,
        }

    def _field_metadata(self, field: dict, form: dict) -> dict:
        return {
            "form_id": form.get("form_id"),
            "field": field.get("name") or field.get("id"),
            "frame": field.get("frame") or form.get("frame"),
        }

    def _field_tag(self, field: dict) -> str:
        return str(field.get("tag", "") or "").lower()

    def _field_type(self, field: dict) -> str:
        return str(field.get("type", "") or "").lower()
