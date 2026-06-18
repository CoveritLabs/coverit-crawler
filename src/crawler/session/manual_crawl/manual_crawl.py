import asyncio
import logging
from src.crawler.session.base import CrawlSessionBase
from src.crawler.session.manual_crawl.recording_mapper import map_steps_to_actions
from src.crawler.session.sequence import CrawlSessionSequenceMixin

logger = logging.getLogger(__name__)


with open("./recording.js", "r", encoding="utf-8") as script_file:
    RECORDING_JS = script_file.read()

class ManualCrawlSession(CrawlSessionBase, CrawlSessionSequenceMixin):
    async def run_crawl(self) -> None:
        try:
            self.headless = False
            self.browser.headless = False
            await self.initialize()
            self._recorded_steps = []
            context = self.browser._require_context()
            await context.expose_function("__reportStep", lambda step: self._recorded_steps.append(step))
            await context.add_init_script(RECORDING_JS)

            await self.browser.navigate(self.base_url)
            await self.browser.wait_for_settle()
            current_state = await self.browser.capture_state()
            await self.add_to_queue(current_state)
            
            print(f"\nManual Crawl Session live on {self.base_url}. Press Ctrl+C to close.\n")

            while True:
                await asyncio.sleep(0.2)

                if not self.browser.context or len(self.browser.context.pages) == 0:
                    break

                new_hash = await self.browser.get_state_hash()

                if new_hash != current_state.state_hash:
                    self.graph_builder.set_state_properties(self.session_id, new_hash, props)
                    steps_to_process = list(self._recorded_steps)
                    self._recorded_steps.clear()
                    new_state = await self.browser.capture_state()
                    actions = map_steps_to_actions(steps_to_process, fallback_url=new_state.url)
                    await self.add_to_queue(new_state)
                    transition = self._build_transition(current_state, new_state, actions)
                    await self.add_transition(transition)

                    logger.info(f"Generated Transition: {transition.action_description}")
                    current_state = new_state

        except KeyboardInterrupt:
            print("\nClosing manual session and committing graph structure...")
        finally:
            await self.cleanup()
    
