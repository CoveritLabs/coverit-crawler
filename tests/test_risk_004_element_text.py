from src.crawler.risk import RiskClassifier
from src.models import CrawlAction


def test_risk_classifier_matches_element_text():
    classifier = RiskClassifier(("cancel",))
    assert classifier.is_risky(CrawlAction(action_type="click"), element={"text": "Cancel subscription"})
