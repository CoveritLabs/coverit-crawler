from src.crawler.session.sequence_builders import sequence_description
from src.models import CrawlAction


def test_sequence_description_for_single_action():
    action = CrawlAction(action_type="click", description="Click save")
    assert sequence_description([action]) == "Click save"
