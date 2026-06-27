import numpy as np

from src.crawler.semantic_engine.vector_math import cosine


def test_cosine_empty_vector_uses_empty_value():
    assert cosine(np.array([]), np.array([1.0]), empty_value=0.5) == 0.5
