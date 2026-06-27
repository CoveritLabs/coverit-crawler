import numpy as np

from src.crawler.semantic_engine.vector_math import cosine


def test_cosine_identical_vectors_is_one():
    assert cosine(np.array([1.0, 0.0]), np.array([1.0, 0.0])) == 1.0
