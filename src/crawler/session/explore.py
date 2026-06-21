from __future__ import annotations

import hashlib
import logging

from src.crawler import ActionType, HtmlTag, InputType
from src.crawler.replay import StateReplayInfo
from src.models import AbstractState, CrawlAction
from src.utils import (
    element_identity_key,
    element_label,
    element_tag,
    element_tag_hint,
    element_type,
    is_button,
    is_non_http_href,
    is_text_input,
    stable_json_dumps,
    supports_enter_submission,
    text_input_label,
)

logger = logging.getLogger(__name__)


class CrawlSessionExploreMixin:
    async def _explore_state(self, current: AbstractState) -> None:
        try:
            if not await self._replay_state(current):
                return

            await self._prepare_state()

            current_info = await self._get_current_state_info(current)

            if not current_info or not self.executor:
                return

            state_elements = await self.browser.get_interactable_elements()

            if self._semantic_engine:
                comparison = await self._semantic_engine.register_state(
                    current.state_hash,
                    state_elements,
                )
                diagnostics = self._semantic_engine.explain_comparison(comparison)
                logger.debug("State %s: %s", current.state_hash, diagnostics)

            await self._explore_forms(current, current_info)
            await self._explore_elements(current, current_info, state_elements)
        finally:
            await self.graph_builder.mark_state_explored(
                self.session_id,
                current.state_hash,
                crawl_session_id=self.crawl_session_id,
            )

    async def _explore_forms(
        self,
        current: AbstractState,
        current_info: StateReplayInfo,
    ) -> None:
        forms = await self.browser.get_forms()

        for form in forms:
            if not self._within_limits():
                break

            await self._wait_permission()
            await self._process_form(form, current, current_info)

            if not await self._replay_after_action(current):
                return

    async def _explore_elements(
        self,
        current: AbstractState,
        current_info: StateReplayInfo,
        state_elements: list[dict] | None = None,
    ) -> None:
        elements = state_elements or await self.browser.get_interactable_elements()
        processed = 0
        for element in elements:
            if processed >= self._settings.MAX_ELEMENTS_PER_STATE:
                break

            if not self._within_limits():
                break

            if not self._should_process_element(element, elements):
                continue

            await self._wait_permission()
            await self._process_element(element, current, current_info)

            processed += 1

    async def _process_form(
        self,
        form: dict,
        current: AbstractState,
        current_info: StateReplayInfo,
    ) -> None:
        if not self.executor:
            return

        actions = self.executor.plan_form_submission(form)

        if not actions:
            return

        primary = actions[-1]

        if self._should_defer_action(primary, form.get("submit")):
            await self._defer_work(current, actions, form.get("submit"))
            return

        await self._execute_action_sequence(current, current_info, actions)

    async def _process_element(
        self,
        element: dict,
        current: AbstractState,
        current_info: StateReplayInfo,
    ) -> None:
        selector = self.browser.get_selector_for_element(element)

        if not selector:
            return

        sequences = self._plan_element_sequences(element, selector)

        for actions in sequences:
            if not self._within_limits():
                return

            primary = actions[-1]

            if self._should_defer_action(primary, element):
                await self._defer_work(current, actions, element)
                continue

            await self._execute_action_sequence(current, current_info, actions)

            if not await self._replay_after_action(current):
                return

    def _should_process_element(
        self,
        element: dict,
        state_elements: list[dict] | None = None,
    ) -> bool:
        if element.get("disabled"):
            return False

        if element.get("in_form"):
            return False

        if self._is_blocked_anchor(element):
            return False

        return True

    def _plan_element_sequences(
        self,
        element: dict,
        selector: str,
    ) -> list[list[CrawlAction]]:
        tag = element_tag(element)
        input_type = element_type(element)

        if tag == HtmlTag.SELECT:
            return self._build_select_sequences(element, selector)

        if tag == HtmlTag.INPUT and input_type in (
            InputType.CHECKBOX,
            InputType.RADIO,
        ):
            return self._build_toggle_sequences(element, selector)

        if is_text_input(element):
            return self._build_text_sequences(element, selector)

        if tag == HtmlTag.ANCHOR:
            return self._build_anchor_sequences(element, selector)

        if is_button(element):
            return self._build_button_sequences(element, selector)

        return self._build_generic_click_sequences(element, selector)

    def _build_select_sequences(
        self,
        element: dict,
        selector: str,
    ) -> list[list[CrawlAction]]:
        sequences: list[list[CrawlAction]] = []

        options = [option for option in element.get("options", []) if option.get("value")]

        for option in options[: self._settings.MAX_SELECT_OPTIONS_PER_ELEMENT]:
            option_text = str(option.get("text") or option.get("value") or "").strip()

            sequences.append(
                [
                    CrawlAction(
                        action_type=ActionType.SELECT,
                        selector=selector,
                        value=str(option["value"]),
                        description=(f"Select '{option_text}' in {element_tag_hint(element)}{element_label(element, selector)}"),
                        metadata={
                            "option": str(option.get("text", "")),
                            "frame": element.get("frame"),
                            "element_key": element_identity_key(element),
                        },
                    )
                ]
            )

        return sequences

    def _build_toggle_sequences(
        self,
        element: dict,
        selector: str,
    ) -> list[list[CrawlAction]]:
        input_type = element_type(element)

        return [
            [
                CrawlAction(
                    action_type=ActionType.CLICK,
                    selector=selector,
                    description=(f"Toggle {input_type} {element_label(element, selector)}"),
                    metadata={
                        "type": input_type,
                        "frame": element.get("frame"),
                        "element_key": element_identity_key(element),
                    },
                )
            ]
        ]

    def _build_text_sequences(
        self,
        element: dict,
        selector: str,
    ) -> list[list[CrawlAction]]:
        if not self.executor:
            return []

        value = self.executor.resolve_value(element)
        label = element_label(element, selector)
        type_label = text_input_label(element)

        base_action = CrawlAction(
            action_type=ActionType.TYPE,
            selector=selector,
            value=value,
            description=f"Type into {type_label} {label}",
            metadata={
                "type": element_type(element),
                "frame": element.get("frame"),
                "element_key": element_identity_key(element),
            },
        )

        sequences = [[base_action]]

        if supports_enter_submission(element):
            sequences.append(
                [
                    base_action,
                    CrawlAction(
                        action_type=ActionType.PRESS,
                        selector=selector,
                        value="Enter",
                        description=f"Press Enter in {label}",
                        metadata={
                            "frame": element.get("frame"),
                            "element_key": element_identity_key(element),
                        },
                    ),
                ]
            )

        return sequences

    def _build_anchor_sequences(
        self,
        element: dict,
        selector: str,
    ) -> list[list[CrawlAction]]:
        href = str(element.get("href", "") or "")
        href_part = f" ({href})" if href else ""

        return [
            [
                CrawlAction(
                    action_type=ActionType.CLICK,
                    selector=selector,
                    description=(f"Click link {element_label(element, selector)}{href_part}"),
                    metadata={
                        "frame": element.get("frame"),
                        "element_key": element_identity_key(element),
                    },
                )
            ]
        ]

    def _build_button_sequences(
        self,
        element: dict,
        selector: str,
    ) -> list[list[CrawlAction]]:
        return [
            [
                CrawlAction(
                    action_type=ActionType.CLICK,
                    selector=selector,
                    description=(f"Click button {element_label(element, selector)}"),
                    metadata={
                        "frame": element.get("frame"),
                        "element_key": element_identity_key(element),
                    },
                )
            ]
        ]

    def _build_generic_click_sequences(
        self,
        element: dict,
        selector: str,
    ) -> list[list[CrawlAction]]:
        return [
            [
                CrawlAction(
                    action_type=ActionType.CLICK,
                    selector=selector,
                    description=(f"Click {element_tag_hint(element)}{element_label(element, selector)}"),
                    metadata={
                        "frame": element.get("frame"),
                        "element_key": element_identity_key(element),
                    },
                )
            ]
        ]

    async def _replay_state(self, current: AbstractState) -> bool:
        if not self.replayer:
            return False

        try:
            return await self.replayer.replay_to(current.state_hash)

        except Exception as e:
            logger.warning(f"Replay failed for state {current.state_hash}: {e}")
            return False

    async def _prepare_state(self) -> None:
        await self.browser.wait_for_settle()

    async def _replay_after_action(self, current: AbstractState) -> bool:
        if not self.replayer:
            return False

        try:
            return await self.replayer.replay_to(current.state_hash)

        except Exception:
            return False

    async def _get_current_state_info(
        self,
        current: AbstractState,
    ) -> StateReplayInfo | None:
        if not self.replayer:
            return None

        return await self.replayer.get_info(current.state_hash)

    def _should_defer_action(
        self,
        action: CrawlAction,
        element: dict | None,
    ) -> bool:
        return self._settings.DEFER_DESTRUCTIVE_ACTIONS and self._risk.is_risky(action, element=element)

    async def _defer_work(
        self,
        current: AbstractState,
        actions: list[CrawlAction],
        element: dict | None,
    ) -> None:
        actions_json = stable_json_dumps([StateReplayInfo.action_to_dict(action) for action in actions])
        element_json = stable_json_dumps(element or {})
        raw_id = stable_json_dumps(
            {
                "source": current.state_hash,
                "actions": actions_json,
                "element": element_json,
            }
        )
        await self.graph_builder.add_deferred_work(
            self.session_id,
            crawl_session_id=self.crawl_session_id,
            work_id=hashlib.sha256(raw_id.encode("utf-8")).hexdigest(),
            source_state_hash=current.state_hash,
            actions_json=actions_json,
            element_json=element_json,
        )

    def _is_blocked_anchor(self, element: dict) -> bool:
        if element_tag(element) != HtmlTag.ANCHOR or self._settings.CLICK_NON_HTTP_LINKS:
            return False

        href = str(element.get("href", "") or "")

        return is_non_http_href(href)
