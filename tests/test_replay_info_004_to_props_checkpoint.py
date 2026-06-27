from src.crawler.replay.info import StateReplayInfo


def test_state_replay_info_to_props_marks_checkpoint():
    props = StateReplayInfo("https://x", checkpoint_state_hash="s").to_neo4j_props(state_hash="s")
    assert props["is_checkpoint"] is True
