from src.crawler.session.sequence_builders import sequence_description
from src.models import CrawlAction


def test_sequence_description_includes_type_value():
    action = CrawlAction(action_type="type", description="Type email", value="a@example.com")
    assert sequence_description([action]) == "Type email value=a@example.com"
