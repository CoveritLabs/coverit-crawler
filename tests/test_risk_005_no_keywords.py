from src.crawler.risk import RiskClassifier
from src.models import CrawlAction


def test_risk_classifier_without_keywords_is_not_risky():
    assert not RiskClassifier(()).is_risky(CrawlAction(description="Delete"))
