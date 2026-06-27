from src.crawler.risk import RiskClassifier
from src.models import CrawlAction


def test_risk_classifier_matches_metadata_values():
    classifier = RiskClassifier(("archive",))
    assert classifier.is_risky(CrawlAction(metadata={"intent": "archive project"}))
