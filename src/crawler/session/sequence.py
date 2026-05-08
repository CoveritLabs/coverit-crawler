from __future__ import annotations

import logging

from src.crawler.fingerprints import (
    action_attempt_fingerprint,
    action_key_fingerprint,
    transition_fingerprint,
)
from src.crawler.replay import StateReplayInfo
from src.crawler.session.types import DeferredWorkItem
from src.crawler.session.sequence_builders import (
    sequence_description,
    sequence_value_for_graph,
    sequence_digest,
)
from src.utils import is_http_url, is_same_domain, normalize_url, normalize_checkpoint_url
from src.models import AbstractState, AbstractTransition, CrawlAction

logger = logging.getLogger(__name__)


class CrawlSessionSequenceMixin:
    async def _execute_action_sequence(
        self,
        source: AbstractState,
        source_info: StateReplayInfo,
        actions: list[CrawlAction],
    ) -> None:
        if not self.executor or not self.replayer or not actions:
            return

        await self._wait_permission()

        primary = actions[-1]
        primary.metadata = dict(primary.metadata or {})
        primary.metadata["sequence_digest"] = sequence_digest(actions)
        primary.metadata["sequence_len"] = len(actions)

        scope_url = normalize_url(
            getattr(source, "url", "") or source_info.checkpoint_url or ""
        )

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
                if not is_same_domain(scope_url, url):
                    continue

                self._deferred_work.append(
                    DeferredWorkItem(
                        source_state=source,
                        actions=[CrawlAction(action_type="navigate", value=url, description="Navigate to popup URL")],
                        element=None,
                    )
                )

            new_url = await self.browser.get_current_url()

            if not is_same_domain(scope_url, new_url):
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

    def _build_transition(
        self,
        source: AbstractState,
        target: AbstractState,
        actions: list[CrawlAction],
    ) -> AbstractTransition:
        primary = actions[-1]

        fp = transition_fingerprint(
            session_id=str(self.session_id),
            source_state_hash=source.state_hash,
            target_state_hash=target.state_hash,
            action=primary,
        )

        locator_value = primary.selector or primary.value

        return AbstractTransition(
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
            )

        fallback_actions = list(getattr(current_info, "fallback_actions", []))

        return StateReplayInfo(
            checkpoint_url=current_info.checkpoint_url,
            checkpoint_state_hash=current_info.checkpoint_state_hash,
            checkpoint_kind=current_info.checkpoint_kind,
            actions=seq_actions,
            fallback_checkpoint_url=getattr(current_info, "fallback_checkpoint_url", None),
            fallback_checkpoint_state_hash=getattr(current_info, "fallback_checkpoint_state_hash", None),
            fallback_actions=fallback_actions + seq_actions if getattr(current_info, "fallback_checkpoint_url", None) else fallback_actions,
        )

    async def _persist_replay_artifacts(
        self,
        *,
        state_hash: str,
        info: StateReplayInfo,
        persist_storage_state: bool,
    ) -> None:
        props = info.to_neo4j_props(state_hash=state_hash)

        await self.graph_builder.set_state_properties(self.session_id, state_hash, props)

        if not persist_storage_state:
            return

        storage_state = await self.browser.export_storage_state()

        await self.graph_builder.set_state_properties(
            self.session_id,
            state_hash,
            {"checkpoint_storage_state_json": storage_state},
        )

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