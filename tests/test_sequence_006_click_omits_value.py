from src.crawler.session.sequence_builders import sequence_value_for_graph
from src.models import CrawlAction


def test_sequence_value_for_graph_omits_click_value():
    action = CrawlAction(action_type="click", selector="#save", value="ignored", description="Save")
    assert '"v":""' in sequence_value_for_graph([action])
