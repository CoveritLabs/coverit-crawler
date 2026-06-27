import numpy as np

from src.crawler.semantic_engine.vector_math import l2_normalize


def test_l2_normalize_unit_length():
    assert np.allclose(l2_normalize(np.array([3.0, 4.0])), np.array([0.6, 0.8]))
