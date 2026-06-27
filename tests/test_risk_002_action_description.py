from src.crawler.risk import RiskClassifier
from src.models import CrawlAction


def test_risk_classifier_matches_action_description():
    classifier = RiskClassifier(("delete",))
    assert classifier.is_risky(CrawlAction(description="Delete account"))
