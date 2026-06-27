from types import SimpleNamespace

from src.crawler.risk import RiskClassifier


def test_risk_classifier_from_settings_splits_keywords():
    classifier = RiskClassifier.from_settings(SimpleNamespace(DESTRUCTIVE_KEYWORDS="delete, remove"))
    assert classifier.keywords == ("delete", "remove")
