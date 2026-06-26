import asyncio
import json
import logging
import sys

from src.crawler.session.base import CrawlSessionBase
from src.crawler.session.manual_crawl.recording_mapper import map_steps_to_actions
from src.crawler.session.sequence import CrawlSessionSequenceMixin
from src.models.graph import AbstractState

logger = logging.getLogger(__name__)

with open("src/crawler/session/manual_crawl/action_recorder.js", "r", encoding="utf-8") as script_file:
    RECORDING_JS = script_file.read()


def _action_value_is_labelable(value: str) -> bool:
    try:
        actions = json.loads(value or "")
    except Exception:
        return False
    if not isinstance(actions, list) or not actions:
        return False
    return all(
        isinstance(action, dict) and bool(str(action.get("s") or "").strip())
        for action in actions
    )


def _transition_is_labelable(transition) -> bool:
    return bool(str(transition.locator_value or "").strip()) and _action_value_is_labelable(
        transition.action_value
    )


class ManualCrawlSession(CrawlSessionBase, CrawlSessionSequenceMixin):
    async def run_crawl(self):
        self._recording_state = False
        self._exit_session = False
        self._recorded_transitions = []
        self._recorded_steps = []
        self._recorded_storage_state_json = []
        self._recorded_states: list[AbstractState] = []
        self._recording_start_idx = 0

        async def listen_for_input():
            loop = asyncio.get_event_loop()
            print("\n--- Manual Crawl Controls ---")
            print("Type 's' + Enter to Start recording for manual flow")
            print("Type 'q' + Enter to stop recording and end session \n")
            print("Type 'b' + Enter to Build Bug Graph\n")
            while not self._exit_session:
                cmd = await loop.run_in_executor(None, sys.stdin.readline)
                cmd = cmd.strip().lower()
                if cmd == "s":
                    if self._recording_state:
                        print("Already recording")
                    else:
                        print("Recording started")
                        self._recording_state = True
                elif cmd == "q":
                    self._exit_session = True
                    break
                elif cmd == "b":
                    print("Building bug graph from recorded session...")
                    await self.build_bug_graph()
                    print("Bug graph build complete.")

        listener_task = asyncio.create_task(listen_for_input())

        try:
            self.headless = False
            self.browser.headless = False

            await self.initialize()
            context = self.browser._require_context()

            await context.expose_function("__reportStep", lambda step: self._recorded_steps.append(step))
            await context.add_init_script(RECORDING_JS)

            await self.browser.navigate(self.base_url)
            await self.browser.wait_for_settle()

            current_state = await self.browser.capture_state()
            self._recorded_states.append(current_state)
            self._recorded_storage_state_json.append(await self.browser.export_storage_state())

            print(f"\nManual Crawl Session live on {self.base_url}.\n")

            while not self._exit_session:
                await asyncio.sleep(0.1)

                if not self.browser.context or len(self.browser.context.pages) == 0:
                    break

                new_hash = await self.browser.get_state_hash()

                if new_hash != current_state.state_hash:
                    steps_to_process = list(self._recorded_steps)
                    self._recorded_steps.clear()

                    new_state = await self.browser.capture_state()

                    if new_state.url != current_state.url and not self._recording_state:
                        self._recording_start_idx = max(0, len(self._recorded_states) - 1)

                    self._recorded_storage_state_json.append(await self.browser.export_storage_state())

                    actions = [
                        action
                        for action in map_steps_to_actions(steps_to_process, fallback_url=current_state.url)
                        if str(action.selector or "").strip()
                    ]
                    self._recorded_states.append(new_state)
                    if not actions:
                        current_state = new_state
                        continue

                    transition = self._build_transition(current_state, new_state, actions)
                    if not _transition_is_labelable(transition):
                        current_state = new_state
                        continue
                    self._recorded_transitions.append(transition)

                    logger.info(f"Generated Transition: {transition.action_description}")
                    current_state = new_state

        except KeyboardInterrupt:
            print("\nManual session interrupted by user.")
        finally:
            listener_task.cancel()
            print("Committing graph structure and cleaning up...")
            await self.build_recorded_graph()
            await self.cleanup()

    async def build_recorded_graph(self) -> None:
        if not self._recorded_states:
            return

        start_idx = self._recording_start_idx if self._recording_start_idx is not None else 0

        await self._build_graph_starting_from(start_idx, is_bug_graph=False)

    async def build_bug_graph(self) -> None:
        await self._build_graph_starting_from(0, is_bug_graph=True)

    async def _build_graph_starting_from(self, start_idx: int, is_bug_graph: bool = False):
        if not self._recorded_states or start_idx >= len(self._recorded_states):
            return {"final_state_hash": None, "transitions": []}

        for i in range(start_idx, len(self._recorded_states)):
            await self.add_to_queue(self._recorded_states[i])
            await self.graph_builder.set_state_properties(
                self.graph_id,
                self._recorded_states[i].state_hash,
                {"checkpoint_storage_state_json": self._recorded_storage_state_json[i]},
            )

        for i in range(start_idx, len(self._recorded_transitions)):
            transition = self._recorded_transitions[i]
            if _transition_is_labelable(transition):
                await self.add_transition(transition)
