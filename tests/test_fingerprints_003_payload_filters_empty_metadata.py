from src.crawler.fingerprints import action_identity_payload
from src.models import CrawlAction


def test_action_identity_payload_filters_empty_metadata_values():
    payload = action_identity_payload(CrawlAction(metadata={"field": "", "option": None}))
    assert payload["metadata"] == {}
