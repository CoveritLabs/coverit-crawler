from src.crawler.fingerprints import best_effort_action_value
from src.models import CrawlAction


def test_best_effort_action_value_returns_type_value():
    assert best_effort_action_value(CrawlAction(action_type="type", value="abc")) == "abc"
