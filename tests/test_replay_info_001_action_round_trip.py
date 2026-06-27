from src.crawler.replay.info import StateReplayInfo
from src.models import CrawlAction


def test_state_replay_info_action_round_trips_dict():
    action = CrawlAction(action_id="a1", action_type="click", selector="#x", metadata={"k": "v"})
    assert StateReplayInfo.action_from_dict(StateReplayInfo.action_to_dict(action)) == action
