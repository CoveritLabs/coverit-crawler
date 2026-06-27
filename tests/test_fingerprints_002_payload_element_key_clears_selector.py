from src.crawler.fingerprints import action_identity_payload
from src.models import CrawlAction


def test_action_identity_payload_clears_selector_when_element_key_present():
    action = CrawlAction(action_type="click", selector="#dynamic", metadata={"element_key": "stable"})
    assert action_identity_payload(action)["selector"] == ""
