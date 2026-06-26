from __future__ import annotations

import json
import logging

from src.crawler.fingerprints import (
    action_attempt_fingerprint,
    action_key_fingerprint,
    transition_fingerprint,
)
from src.crawler.replay import StateReplayInfo
from src.crawler.semantic_engine import semantic_priority_penalty
from src.crawler.session.sequence_builders import (
    sequence_description,
    sequence_digest,
    sequence_value_for_graph,
)
from src.models import AbstractState, AbstractTransition, CrawlAction
from src.utils import is_http_url, is_same_domain, normalize_checkpoint_url, normalize_url

logger = logging.getLogger(__name__)


class CrawlSessionSequenceMixin:
    async def _execute_action_sequence(
        self,
        source: AbstractState,
        source_info: StateReplayInfo,
        actions: list[CrawlAction],
    ) -> AbstractState | None:
        if not self.executor or not self.replayer or not actions:
            return None

        await self._wait_permission()

        primary = actions[-1]
        primary.metadata = dict(primary.metadata or {})
        primary.metadata["sequence_digest"] = sequence_digest(actions)
        primary.metadata["sequence_len"] = len(actions)

        scope_url = normalize_url(getattr(source, "url", "") or source_info.checkpoint_url or "")

        action_key = action_key_fingerprint(primary)
        attempt_fp = action_attempt_fingerprint(source.state_hash, primary)

        if not await self.graph_builder.mark_action_attempted(
            self.graph_id,
            source.state_hash,
            attempt_fp,
            session_id=self.session_id,
        ):
            return None

        can_run = await self.graph_builder.try_increment_action_repeat(
            self.graph_id,
            scope=scope_url,
            action_key=action_key,
            max_repeats=int(getattr(self._settings, "MAX_ACTION_REPEATS_PER_URL", 2)),
            session_id=self.session_id,
        )
        if not can_run:
            return None

        initial_page_count = len(self.browser.context.pages) if self.browser.context else 0

        try:
            for action in actions:
                await self._wait_permission()
                await self.executor.execute_action(action)

            await self.browser.wait_for_settle()

            popup_urls = await self.browser.collect_and_close_pages_opened_since(initial_page_count)

            for url in popup_urls:
                if not url or not is_http_url(url):
                    continue
                if not is_same_domain(scope_url, url):
                    continue

                await self._defer_work(
                    source,
                    [CrawlAction(action_type="navigate", value=url, description="Navigate to popup URL")],
                    None,
                )

            new_url = await self.browser.get_current_url()

            if not is_same_domain(scope_url, new_url):
                logger.warning(f"Left domain: {new_url}")
                await self.replayer.replay_to(source.state_hash)
                return None

            new_state = await self.browser.capture_state()
            source_url = normalize_url(
                getattr(source, "url", "") or source_info.checkpoint_url or ""
            )
            reached_url = normalize_url(new_url)
            if new_state.state_hash == source.state_hash and reached_url == source_url:
                return None

            target_state = new_state
            priority_penalty: float | None = None
            semantic_match_hash = ""
            semantic_match_confidence: float | None = None
            semantic_match_reason = ""
            semantic_match_scores: dict[str, float] = {}

            if self._semantic_engine:
                new_state_elements = await self.browser.get_interactable_elements()
                comparison = await self._semantic_engine.register_state(
                    new_state.state_hash,
                    new_state_elements,
                )
                diagnostics = self._semantic_engine.explain_comparison(comparison)
                logger.debug("State comparison diagnostics: %s", diagnostics)
                if comparison.reason != "already_registered":
                    priority_penalty = semantic_priority_penalty(comparison)
                    semantic_match_hash = comparison.matched_state_hash or ""
                    semantic_match_confidence = comparison.confidence
                    semantic_match_reason = comparison.reason
                    semantic_match_scores = comparison.scores
                if (
                    comparison.reason != "already_registered"
                    and comparison.is_equivalent
                    and comparison.matched_state_hash
                ):
                    logger.info(
                        "State %s is equivalent to %s (confidence %.3f). Deprioritizing exploration.",
                        new_state.state_hash,
                        comparison.matched_state_hash,
                        comparison.confidence,
                    )

            info = self._build_replay_info(source_info, actions, reached_url=new_url)

            if not info.checkpoint_state_hash:
                info.checkpoint_state_hash = new_state.state_hash

            await self.add_to_queue(
                new_state,
                semantic_priority_penalty=priority_penalty,
                matched_state_hash=semantic_match_hash,
                confidence=semantic_match_confidence,
                reason=semantic_match_reason,
                scores=semantic_match_scores,
            )
            updated = await self.replayer.register(new_state.state_hash, info)

            if updated:
                await self._persist_replay_artifacts(
                    state_hash=new_state.state_hash,
                    info=info,
                    persist_storage_state=(info.checkpoint_state_hash == new_state.state_hash),
                )

            await self.add_transition(self._build_transition(source, target_state, actions))

            return target_state

        except Exception as e:
            logger.warning(f"Error on action sequence ({primary.action_type}): {e}")
            try:
                await self.replayer.replay_to(source.state_hash)
            except Exception:
                pass
            return None

    def _build_transition(
        self,
        source: AbstractState,
        target: AbstractState,
        actions: list[CrawlAction],
    ) -> AbstractTransition:
        primary = actions[-1]

        fp = transition_fingerprint(
            graph_id=str(self.graph_id),
            source_state_hash=source.state_hash,
            target_state_hash=target.state_hash,
            action=primary,
        )

        locator_value = primary.selector or primary.value

        return AbstractTransition(
            graph_id=str(self.graph_id),
            session_id=str(self.session_id),
            transition_id=fp,
            source_state_hash=source.state_hash,
            target_state_hash=target.state_hash,
            action_type=primary.action_type,
            action_description=sequence_description(actions),
            locator_id=primary.action_id,
            locator_value=locator_value,
            action_value=sequence_value_for_graph(actions),
            action_fingerprint=fp,
            action_stable_key=action_key_fingerprint(primary),
        )

    def _build_replay_info(
        self,
        current_info: StateReplayInfo,
        actions: list[CrawlAction],
        *,
        reached_url: str,
    ) -> StateReplayInfo:
        reached = normalize_checkpoint_url(reached_url)
        parent = normalize_checkpoint_url(current_info.checkpoint_url)

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
                fallback_storage_state=current_info.storage_state,
            )

        fallback_actions = list(getattr(current_info, "fallback_actions", []))

        return StateReplayInfo(
            checkpoint_url=current_info.checkpoint_url,
            checkpoint_state_hash=current_info.checkpoint_state_hash,
            checkpoint_kind=current_info.checkpoint_kind,
            actions=seq_actions,
            storage_state=current_info.storage_state,
            fallback_checkpoint_url=getattr(current_info, "fallback_checkpoint_url", None),
            fallback_checkpoint_state_hash=getattr(current_info, "fallback_checkpoint_state_hash", None),
            fallback_actions=fallback_actions + seq_actions if getattr(current_info, "fallback_checkpoint_url", None) else fallback_actions,
            fallback_storage_state=getattr(current_info, "fallback_storage_state", None),
        )

    async def _persist_replay_artifacts(
        self,
        *,
        state_hash: str,
        info: StateReplayInfo,
        persist_storage_state: bool,
    ) -> None:
        props = info.to_neo4j_props(state_hash=state_hash)

        await self.graph_builder.set_state_properties(self.graph_id, state_hash, props)

        if not persist_storage_state:
            return

        storage_state = await self.browser.export_storage_state()

        await self.graph_builder.set_state_properties(
            self.graph_id,
            state_hash,
            {"checkpoint_storage_state_json": storage_state},
        )

    async def _run_deferred_item(self, item: dict) -> None:
        if not self.replayer:
            return

        await self._wait_permission()
        work_id = str(item.get("work_id") or "")

        try:
            source_hash = str(item.get("source_state_hash") or "")
            actions = [
                StateReplayInfo.action_from_dict(raw)
                for raw in json.loads(str(item.get("actions_json") or "[]"))
                if isinstance(raw, dict)
            ]
            if not source_hash or not actions:
                return

            ok = await self.replayer.replay_to(source_hash)
            if not ok:
                return
            source_info = await self.replayer.get_info(source_hash)
            if not source_info:
                return

            source_state = AbstractState(state_hash=source_hash, url=source_info.checkpoint_url, html="")
            await self._execute_action_sequence(source_state, source_info, actions)
        except Exception:
            return
        finally:
            if work_id:
                await self.graph_builder.mark_deferred_work_processed(
                    self.graph_id,
                    work_id,
                    session_id=self.session_id,
                )
