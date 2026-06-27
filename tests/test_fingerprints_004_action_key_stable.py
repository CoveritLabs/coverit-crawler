from src.crawler.fingerprints import action_key_fingerprint
from src.models import CrawlAction


def test_action_key_fingerprint_is_stable_for_equivalent_actions():
    left = CrawlAction(action_type="click", selector="#save")
    right = CrawlAction(action_type="click", selector="#save")
    assert action_key_fingerprint(left) == action_key_fingerprint(right)
