import numpy as np

from src.crawler.semantic_engine.vector_math import softmax


def test_softmax_rows_sum_to_one():
    assert np.allclose(softmax(np.array([[1.0, 2.0]])).sum(axis=1), np.array([1.0]))
