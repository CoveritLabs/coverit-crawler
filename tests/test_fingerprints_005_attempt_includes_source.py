from src.crawler.fingerprints import action_attempt_fingerprint
from src.models import CrawlAction


def test_action_attempt_fingerprint_includes_source_state():
    action = CrawlAction(action_type="click", selector="#save")
    assert action_attempt_fingerprint("s1", action) != action_attempt_fingerprint("s2", action)
