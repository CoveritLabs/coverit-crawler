from src.crawler.fingerprints import transition_fingerprint
from src.models import CrawlAction


def test_transition_fingerprint_includes_target_state():
    action = CrawlAction(action_type="click", selector="#save")
    left = transition_fingerprint(graph_id="g", source_state_hash="s", target_state_hash="t1", action=action)
    right = transition_fingerprint(graph_id="g", source_state_hash="s", target_state_hash="t2", action=action)
    assert left != right
