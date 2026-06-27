from src.crawler.session.sequence_builders import sequence_digest
from src.models import CrawlAction


def test_sequence_digest_changes_when_value_changes():
    left = [CrawlAction(action_type="type", selector="#email", value="a")]
    right = [CrawlAction(action_type="type", selector="#email", value="b")]
    assert sequence_digest(left) != sequence_digest(right)
