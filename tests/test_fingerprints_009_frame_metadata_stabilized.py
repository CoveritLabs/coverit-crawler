from src.crawler.fingerprints import action_identity_payload
from src.models import CrawlAction


def test_action_identity_payload_keeps_stable_frame_fields():
    action = CrawlAction(metadata={"frame": {"name": "main", "ignored": "x"}})
    assert action_identity_payload(action)["metadata"]["frame"] == {"name": "main", "id": "", "src": "", "url": ""}
