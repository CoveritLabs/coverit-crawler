from src.crawler.replay.info import StateReplayInfo


def test_state_replay_info_from_empty_record_returns_none():
    assert StateReplayInfo.from_neo4j_record({}) is None
