from src.crawler.session.sequence_builders import sequence_description
from src.models import CrawlAction


def test_sequence_description_joins_multiple_actions():
    actions = [CrawlAction(action_type="click", description="Open"), CrawlAction(action_type="press", value="Enter")]
    assert sequence_description(actions) == "Sequence (2): Open -> press value=Enter"
