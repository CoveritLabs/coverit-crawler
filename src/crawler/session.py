import asyncio
import hashlib
import logging
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional, Set
from uuid import uuid4

from ..browser.engine import BrowserEngine
from ..config import Config, config
from ..models.graph import AbstractState, AbstractTransition, CrawlAction
from .action_limits import ActionRepeatLimiter
from .executor import EventExecutor, StateReplayer, StateReplayInfo
from .fingerprints import (
    action_attempt_fingerprint,
    action_key_fingerprint,
    transition_fingerprint,
)
from .element_hints import element_display_hint
from .serialization import stable_json_dumps
from .risk import RiskClassifier, is_http_url, is_non_http_href

logger = logging.getLogger(__name__)


@dataclass
class DeferredWorkItem:
    source_state: AbstractState
    actions: List[CrawlAction]
    element: Optional[dict] = None


class CrawlSession:
    def __init__(
        self,
        base_url: str,
        graph_builder,
        config_path: Optional[str] = None,
        session_id: Optional[str] = None,
        headless: Optional[bool] = None,
        max_states: Optional[int] = None,
        max_transitions: Optional[int] = None,
        timeout_ms: Optional[int] = None,
        input_defaults: Optional[dict] = None,
        *,
        browser: Optional[BrowserEngine] = None,
        settings: Config = config,
        risk_classifier: Optional[RiskClassifier] = None,
        run_permission: Optional[asyncio.Event] = None,
    ):
        self._settings = settings
        self._run_permission = run_permission
        self.base_url = base_url
        self.graph_builder = graph_builder
        self.headless = settings.HEADLESS if headless is None else headless
        self.config_path = config_path
        self._input_defaults = input_defaults
        self.session_id = session_id or str(uuid4())

        self.discovered_states: Set[str] = set()
        self.discovery_queue: Deque[AbstractState] = deque()
        self._deferred_work: Deque[DeferredWorkItem] = deque()
        self._tried_actions_by_state: Dict[str, Set[str]] = {}
        self._seen_transition_ids: Set[str] = set()
        self._risk = risk_classifier or RiskClassifier.from_settings(settings)
        self._login_attempts = 0
        self._action_repeat_limiter = ActionRepeatLimiter(
            max_repeats_per_scope=int(getattr(settings, "MAX_ACTION_REPEATS_PER_URL", 2))
        )

        self.browser = browser or BrowserEngine(
            headless=self.headless,
            timeout_ms=timeout_ms,
            settings=settings,
        )
        self.executor: Optional[EventExecutor] = None
        self.replayer: Optional[StateReplayer] = None
        self._max_states: int = int(
            max_states if max_states is not None else getattr(settings, "MAX_STATES", 1000)
        )
        self._max_transitions: int = int(
            max_transitions if max_transitions is not None else getattr(settings, "MAX_TRANSITIONS", 5000)
        )
        self._state_count: int = 0
        self._transition_count: int = 0

    @property
    def state_count(self) -> int:
        return self._state_count

    @property
    def transition_count(self) -> int:
        return self._transition_count

    async def _wait_permission(self) -> None:
        if self._run_permission is not None:
            await self._run_permission.wait()

    async def initialize(self) -> None:
        await self.browser.start()
        self.executor = EventExecutor(
            self.browser,
            config_path=self.config_path,
            input_defaults=self._input_defaults,
        )
        self.replayer = StateReplayer(self.browser, self.executor, self._settings)
        logger.info("Crawl session initialized")

    async def cleanup(self) -> None:
        await self.browser.stop()
        logger.info("Crawl session completed")

    async def add_to_queue(self, state: AbstractState) -> None:
        if state.state_hash in self.discovered_states:
            return
        await self._wait_permission()
        self._state_count += 1
        self.discovered_states.add(state.state_hash)
        self.discovery_queue.append(state)
        await self.graph_builder.add_state(self.session_id, state)

    def get_next_state(self) -> Optional[AbstractState]:
        return self.discovery_queue.popleft() if self.discovery_queue else None

    async def add_transition(self, transition: AbstractTransition) -> None:
        if transition.transition_id in self._seen_transition_ids:
            return
        await self._wait_permission()
        self._seen_transition_ids.add(transition.transition_id)
        self._transition_count += 1
        await self.graph_builder.add_transition(transition)
        if self.executor:
            self.executor.log_transition(transition)

    @property
    def is_complete(self) -> bool:
        return not self.discovery_queue

    def _within_limits(self) -> bool:
        return self._state_count < self._max_states and self._transition_count < self._max_transitions

    async def run_crawl(self) -> None:
        try:
            await self.initialize()
            await self._seed_initial_state()

            while self._within_limits():
                await self._wait_permission()
                if not self.is_complete:
                    current = self.get_next_state()
                    if current:
                        logger.info(
                            f"Exploring state {current.state_hash} "
                            f"({self._state_count}/{self._max_states} states, "
                            f"{self._transition_count}/{self._max_transitions} transitions)"
                        )
                        await self._explore_state(current)
                    continue

                if self._settings.DEFER_DESTRUCTIVE_ACTIONS and self._deferred_work:
                    item = self._deferred_work.popleft()
                    await self._run_deferred_item(item)
                    continue

                break

            logger.info(
                f"Crawl complete. States: {self._state_count}, "
                f"Transitions: {self._transition_count}"
            )
        except Exception as e:
            logger.error(f"Crawl failed: {e}", exc_info=True)
            raise
        finally:
            await self.cleanup()

    async def _seed_initial_state(self) -> None:
        await self._wait_permission()
        await self.browser.navigate(self.base_url)
        await self.browser.wait_for_settle()

        await self._attempt_login_if_needed()
        await self.browser.wait_for_settle()

        initial_state = await self.browser.capture_state()
        if not self.replayer:
            return
        await self.add_to_queue(initial_state)

        info = StateReplayInfo(
            checkpoint_url=initial_state.url,
            checkpoint_state_hash=initial_state.state_hash,
            checkpoint_kind="initial",
        )
        updated = self.replayer.register(initial_state.state_hash, info)
        if updated:
            await self._persist_replay_artifacts(state_hash=initial_state.state_hash, info=info, persist_storage_state=True)
        logger.info(f"Initial state: {initial_state.state_hash} at {initial_state.url}")

    async def _attempt_login_if_needed(self) -> None:
        if self._login_attempts >= 2:
            return
        if not self.executor:
            return

        await self._wait_permission()

        forms = await self.browser.get_forms()
        login_form = self._select_login_form(forms)
        if not login_form:
            return

        self._login_attempts += 1
        actions = self.executor.plan_form_submission(login_form)
        if not actions:
            return

        for action in actions:
            await self._wait_permission()
            await self.executor.execute_action(action)

    def _select_login_form(self, forms: List[dict]) -> Optional[dict]:
        for form in forms:
            fields = form.get("fields", [])
            if any(str(f.get("type", "")).lower() == "password" for f in fields):
                submit = form.get("submit")
                if submit and submit.get("selector"):
                    return form
        return None

    async def _explore_state(self, current: AbstractState) -> None:
        if not self.replayer:
            return
        try:
            ok = await self.replayer.replay_to(current.state_hash)
            if not ok:
                return
        except Exception as e:
            logger.warning(f"Replay failed for state {current.state_hash}: {e}")
            return

        await self.browser.wait_for_settle()
        await self._attempt_login_if_needed()
        await self.browser.wait_for_settle()

        current_info = self.replayer.get_info(current.state_hash)
        if not current_info or not self.executor:
            return

        forms = await self.browser.get_forms()
        for form in forms:
            if not self._within_limits():
                break
            await self._wait_permission()
            await self._process_form(form, current, current_info)
            try:
                await self.replayer.replay_to(current.state_hash)
            except Exception:
                return

        elements = await self.browser.get_interactable_elements()
        processed = 0
        for element in elements:
            if processed >= self._settings.MAX_ELEMENTS_PER_STATE:
                break
            if not self._within_limits():
                break
            if not self._should_process_element(element):
                continue
            await self._wait_permission()
            await self._process_element(element, current, current_info)
            processed += 1

    async def _process_form(self, form: dict, current: AbstractState, current_info: StateReplayInfo) -> None:
        if not self.executor:
            return

        actions = self.executor.plan_form_submission(form)
        if not actions:
            return

        primary = actions[-1]
        if self._settings.DEFER_DESTRUCTIVE_ACTIONS and self._risk.is_risky(primary, element=form.get("submit")):
            self._deferred_work.append(DeferredWorkItem(source_state=current, actions=actions, element=form.get("submit")))
            return

        await self._execute_action_sequence(current, current_info, actions)

    async def _process_element(self, element: dict, current: AbstractState, current_info: StateReplayInfo) -> None:
        selector = self.browser.get_selector_for_element(element)
        if not selector:
            return

        sequences = self._plan_element_sequences(element, selector)
        for actions in sequences:
            if not self._within_limits():
                return
            primary = actions[-1]
            if self._settings.DEFER_DESTRUCTIVE_ACTIONS and self._risk.is_risky(primary, element=element):
                self._deferred_work.append(DeferredWorkItem(source_state=current, actions=actions, element=element))
                continue
            await self._execute_action_sequence(current, current_info, actions)
            if self.replayer:
                try:
                    await self.replayer.replay_to(current.state_hash)
                except Exception:
                    return

    def _should_process_element(self, element: dict) -> bool:
        if element.get("disabled"):
            return False

        tag = str(element.get("tag", "") or "").lower()
        input_type = str(element.get("type", "") or "").lower()

        if element.get("in_form"):
            if tag == "select":
                return True
            if tag == "input" and input_type in ("checkbox", "radio"):
                return True
            return False

        if tag == "a" and not self._settings.CLICK_NON_HTTP_LINKS:
            href = str(element.get("href", "") or "")
            if is_non_http_href(href):
                return False

        return True

    def _plan_element_sequences(self, element: dict, selector: str) -> List[List[CrawlAction]]:
        tag = str(element.get("tag", "") or "").lower()
        input_type = str(element.get("type", "") or "").lower()
        frame = element.get("frame")

        element_label = element_display_hint(element, label_keys=("aria_label", "label"))
        element_label_or_selector = element_label.strip() or selector
        href = str(element.get("href", "") or "")
        tag_hint = self._element_tag_hint(element)

        if tag == "select":
            options = [o for o in element.get("options", []) if o.get("value")]
            out: List[List[CrawlAction]] = []
            for o in options[: self._settings.MAX_SELECT_OPTIONS_PER_ELEMENT]:
                option_text = str(o.get("text") or o.get("value") or "").strip()
                out.append([
                    CrawlAction(
                        action_type="select",
                        selector=selector,
                        value=str(o["value"]),
                        description=f"Select '{option_text}' in {tag_hint}{element_label_or_selector}",
                        metadata={"option": str(o.get("text", "")), "frame": frame},
                    )
                ])
            return out

        if tag == "input" and input_type in ("checkbox", "radio"):
            label = element_label_or_selector
            return [[
                CrawlAction(
                    action_type="click",
                    selector=selector,
                    description=f"Toggle {input_type} {label}",
                    metadata={"type": input_type, "frame": frame},
                )
            ]]

        if tag in ("input", "textarea") or element.get("contenteditable"):
            if not self.executor:
                return []
            value = self.executor.resolve_value(element)

            label = element_label_or_selector
            type_label = input_type or ("contenteditable" if element.get("contenteditable") else "field")

            sequences: List[List[CrawlAction]] = []
            sequences.append([
                CrawlAction(
                    action_type="type",
                    selector=selector,
                    value=value,
                    description=f"Type into {type_label} {label}",
                    metadata={"type": input_type, "frame": frame},
                )
            ])

            if tag == "input" and input_type in ("text", "search", "email", "tel", "url", "number"):
                sequences.append([
                    CrawlAction(
                        action_type="type",
                        selector=selector,
                        value=value,
                        description=f"Type into {type_label} {label}",
                        metadata={"type": input_type, "frame": frame},
                    ),
                    CrawlAction(
                        action_type="press",
                        selector=selector,
                        value="Enter",
                        description=f"Press Enter in {label}",
                        metadata={"frame": frame},
                    ),
                ])

            return sequences

        if tag == "a":
            href_part = f" ({href})" if href else ""
            return [[
                CrawlAction(
                    action_type="click",
                    selector=selector,
                    description=f"Click link {element_label_or_selector}{href_part}",
                    metadata={"frame": frame},
                )
            ]]

        if tag in ("button",) or element.get("role") == "button" or (tag == "input" and input_type in ("submit", "button")):
            return [[
                CrawlAction(
                    action_type="click",
                    selector=selector,
                    description=f"Click button {element_label_or_selector}",
                    metadata={"frame": frame},
                )
            ]]

        label = element_label_or_selector
        return [[
            CrawlAction(
                action_type="click",
                selector=selector,
                description=f"Click {tag_hint}{label}",
                metadata={"frame": frame},
            )
        ]]

    def _element_tag_hint(self, element: dict) -> str:
        tag = str(element.get("tag", "") or "").lower()
        t = str(element.get("type", "") or "").lower()
        if tag == "input" and t and t not in ("text", "search"):
            return f"{tag}[{t}] "
        return f"{tag} " if tag else ""

    async def _execute_action_sequence(
        self,
        source: AbstractState,
        source_info: StateReplayInfo,
        actions: List[CrawlAction],
    ) -> None:
        if not self.executor or not self.replayer:
            return
        if not actions:
            return

        await self._wait_permission()

        primary = actions[-1]
        primary.metadata = dict(primary.metadata or {})
        primary.metadata["sequence_digest"] = self._sequence_digest(actions)
        primary.metadata["sequence_len"] = len(actions)

        scope_url = self._normalize_url(getattr(source, "url", "") or source_info.checkpoint_url or "")
        action_key = action_key_fingerprint(primary)
        if not self._action_repeat_limiter.can_run(scope=scope_url, action_key=action_key):
            return

        attempt_fp = action_attempt_fingerprint(source.state_hash, primary)
        tried = self._tried_actions_by_state.setdefault(source.state_hash, set())
        if attempt_fp in tried:
            return
        tried.add(attempt_fp)

        initial_page_count = len(self.browser.context.pages) if self.browser.context else 0

        try:
            for action in actions:
                await self._wait_permission()
                await self.executor.execute_action(action)

            await self.browser.wait_for_settle()

            self._action_repeat_limiter.record(scope=scope_url, action_key=action_key)

            popup_urls = await self.browser.collect_and_close_pages_opened_since(initial_page_count)
            for url in popup_urls:
                if not url or not is_http_url(url):
                    continue
                if not self.browser.is_same_domain(scope_url, url):
                    continue
                nav_action = CrawlAction(
                    action_type="navigate",
                    value=url,
                    description="Navigate to popup URL",
                )
                self._deferred_work.append(DeferredWorkItem(source_state=source, actions=[nav_action], element=None))

            new_url = await self.browser.get_current_url()
            if not self.browser.is_same_domain(scope_url, new_url):
                logger.warning(f"Left domain: {new_url}")
                await self.replayer.replay_to(source.state_hash)
                return

            new_state = await self.browser.capture_state()
            if new_state.state_hash == source.state_hash:
                return

            info = self._build_replay_info(source_info, actions, reached_url=new_url)
            if not info.checkpoint_state_hash:
                info.checkpoint_state_hash = new_state.state_hash

            updated = self.replayer.register(new_state.state_hash, info)
            await self.add_to_queue(new_state)
            if updated:
                await self._persist_replay_artifacts(
                    state_hash=new_state.state_hash,
                    info=info,
                    persist_storage_state=(info.checkpoint_state_hash == new_state.state_hash),
                )
            await self.add_transition(self._build_transition(source, new_state, actions))

        except Exception as e:
            logger.warning(f"Error on action sequence ({primary.action_type}): {e}")
            try:
                await self.replayer.replay_to(source.state_hash)
            except Exception:
                pass

    def _build_transition(self, source: AbstractState, target: AbstractState, actions: List[CrawlAction]) -> AbstractTransition:
        primary = actions[-1]
        fp = transition_fingerprint(
            session_id=str(self.session_id),
            source_state_hash=source.state_hash,
            target_state_hash=target.state_hash,
            action=primary,
        )
        locator_value = primary.selector or primary.value
        sequence_value = self._sequence_value_for_graph(actions)
        return AbstractTransition(
            session_id=str(self.session_id),
            transition_id=fp,
            source_state_hash=source.state_hash,
            target_state_hash=target.state_hash,
            action_type=primary.action_type,
            action_description=self._sequence_description(actions),
            locator_id=primary.action_id,
            locator_value=locator_value,
            action_value=sequence_value,
            action_fingerprint=fp,
        )

    def _build_replay_info(self, current_info: StateReplayInfo, actions: List[CrawlAction], *, reached_url: str) -> StateReplayInfo:
        reached = self._normalize_checkpoint_url(reached_url)
        parent = self._normalize_checkpoint_url(current_info.checkpoint_url)

        seq_actions = current_info.actions + list(actions)
        if reached and reached != parent:
            return StateReplayInfo(
                checkpoint_url=reached,
                checkpoint_state_hash="",
                checkpoint_kind="url_change",
                actions=[],
                fallback_checkpoint_url=current_info.checkpoint_url,
                fallback_checkpoint_state_hash=current_info.checkpoint_state_hash,
                fallback_actions=seq_actions,
            )

        fallback_checkpoint_url = getattr(current_info, "fallback_checkpoint_url", None)
        fallback_checkpoint_state_hash = getattr(current_info, "fallback_checkpoint_state_hash", None)
        base_fallback_actions = list(getattr(current_info, "fallback_actions", []))
        combined_fallback_actions = base_fallback_actions + seq_actions if fallback_checkpoint_url else base_fallback_actions

        return StateReplayInfo(
            checkpoint_url=current_info.checkpoint_url,
            checkpoint_state_hash=current_info.checkpoint_state_hash,
            checkpoint_kind=current_info.checkpoint_kind,
            actions=seq_actions,
            fallback_checkpoint_url=fallback_checkpoint_url,
            fallback_checkpoint_state_hash=fallback_checkpoint_state_hash,
            fallback_actions=combined_fallback_actions,
        )

    async def _persist_replay_artifacts(self, *, state_hash: str, info: StateReplayInfo, persist_storage_state: bool) -> None:
        props = info.to_neo4j_props(state_hash=state_hash)
        await self.graph_builder.set_state_properties(self.session_id, state_hash, props)
        if not persist_storage_state:
            return
        storage_state = await self.browser.export_storage_state()
        await self.graph_builder.set_state_properties(
            self.session_id,
            state_hash,
            {"checkpoint_storage_state_json": stable_json_dumps(storage_state)},
        )

    def _normalize_checkpoint_url(self, url: str) -> str:
        u = str(url or "")
        if u.endswith("?"):
            u = u[:-1]
        return u

    def _normalize_url(self, url: str) -> str:
        u = str(url or "")
        if u.endswith("?"):
            u = u[:-1]
        u = u.split("#", 1)[0]
        return u

    def _sequence_description(self, actions: List[CrawlAction]) -> str:
        if not actions:
            return ""
        if len(actions) == 1:
            return actions[0].description

        parts: List[str] = []
        for a in actions[:6]:
            d = str(a.description or a.action_type).strip()
            if d:
                parts.append(d)
        suffix = ""
        if len(actions) > 6:
            suffix = f" … (+{len(actions) - 6} more)"
        return f"Sequence ({len(actions)}): " + " -> ".join(parts) + suffix

    def _sequence_value_for_graph(self, actions: List[CrawlAction]) -> str:
        payload: List[dict] = []
        for a in actions:
            payload.append(
                {
                    "t": a.action_type,
                    "s": a.selector,
                    "v": self._safe_action_value(a),
                    "d": a.description,
                }
            )
        return stable_json_dumps(payload)

    def _safe_action_value(self, action: CrawlAction) -> str:
        if action.action_type == "type":
            meta = action.metadata or {}
            field_type = str(meta.get("type", "") or "").lower()
            field_name = str(meta.get("field", "") or "").lower()
            if field_type == "password" or "pass" in field_name:
                return "<redacted>"
            return "<typed>"
        if action.action_type in ("navigate", "select", "press"):
            return str(action.value or "")
        return ""

    def _sequence_digest(self, actions: List[CrawlAction]) -> str:
        payload = [{"t": a.action_type, "s": a.selector, "v": a.value} for a in actions]
        raw = stable_json_dumps(payload)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    async def _run_deferred_item(self, item: DeferredWorkItem) -> None:
        if not self.replayer:
            return
        await self._wait_permission()
        try:
            ok = await self.replayer.replay_to(item.source_state.state_hash)
            if not ok:
                return
        except Exception:
            return

        source_info = self.replayer.get_info(item.source_state.state_hash)
        if not source_info:
            return

        await self._execute_action_sequence(item.source_state, source_info, item.actions)