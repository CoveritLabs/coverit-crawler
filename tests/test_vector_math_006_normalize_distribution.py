import numpy as np

from src.crawler.semantic_engine.vector_math import normalize_distribution


def test_normalize_distribution_sums_to_one():
    assert np.allclose(normalize_distribution(np.array([1.0, 3.0])), np.array([0.25, 0.75]))
