from src.crawler.session.sequence_builders import sequence_value_for_graph
from src.models import CrawlAction


def test_sequence_value_for_graph_serializes_actions():
    action = CrawlAction(action_type="navigate", selector="", value="https://example.com", description="Go")
    assert sequence_value_for_graph([action]) == '[{"d":"Go value=https://example.com","s":"","t":"navigate","v":"https://example.com"}]'
