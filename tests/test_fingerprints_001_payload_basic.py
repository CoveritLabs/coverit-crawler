from src.crawler.fingerprints import action_identity_payload
from src.models import CrawlAction


def test_action_identity_payload_includes_action_fields():
    payload = action_identity_payload(CrawlAction(action_type="click", selector="#save"))
    assert payload["action_type"] == "click"
    assert payload["selector"] == "#save"
