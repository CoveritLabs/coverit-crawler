from src.crawler.session.sequence_builders import sequence_digest
from src.models import CrawlAction


def test_sequence_digest_is_stable_for_same_actions():
    actions = [CrawlAction(action_type="click", selector="#save")]
    assert sequence_digest(actions) == sequence_digest(actions)
