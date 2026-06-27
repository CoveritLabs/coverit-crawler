import numpy as np

from src.crawler.semantic_engine.vector_math import sigmoid


def test_sigmoid_zero_is_half():
    assert np.allclose(sigmoid(np.array([0.0])), np.array([0.5]))
