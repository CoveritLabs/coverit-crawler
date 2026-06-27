from src.crawler.replay.info import StateReplayInfo


def test_state_replay_info_score_prefers_self_checkpoint():
    info = StateReplayInfo("https://x", checkpoint_state_hash="s")
    assert info.score_for_state("s")[0] == 0
