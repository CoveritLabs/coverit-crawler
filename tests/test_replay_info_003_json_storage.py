from src.crawler.replay.info import StateReplayInfo


def test_state_replay_info_decodes_json_storage_state():
    info = StateReplayInfo.from_neo4j_record({"checkpoint_url": "https://x", "checkpoint_storage_state_json": "{\"a\": 1}"})
    assert info.storage_state == {"a": 1}
