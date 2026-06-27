from src.crawler.fingerprints import best_effort_action_value
from src.models import CrawlAction


def test_best_effort_action_value_ignores_click_value():
    assert best_effort_action_value(CrawlAction(action_type="click", value="abc")) == ""
