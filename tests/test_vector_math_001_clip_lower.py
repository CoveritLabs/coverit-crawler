from src.crawler.semantic_engine.vector_math import clip


def test_clip_applies_lower_bound():
    assert clip(-2.0) == -1.0
