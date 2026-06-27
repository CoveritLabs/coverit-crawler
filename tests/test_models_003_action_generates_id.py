from src.models import CrawlAction


def test_crawl_action_generates_action_id():
    assert CrawlAction().action_id
