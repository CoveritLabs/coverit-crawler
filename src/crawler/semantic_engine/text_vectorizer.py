from __future__ import annotations

import hashlib
import math
from collections import Counter
from dataclasses import dataclass

import numpy as np

from src.crawler.semantic_engine.extractor import normalize_semantic_text
from src.crawler.semantic_engine.vector_math import l2_normalize_rows


@dataclass(frozen=True)
class _TermStats:
    document_frequency: int
    total_frequency: int


class ManualTfidfEncoder:
    def __init__(
        self,
        *,
        analyzer: str = "word",
        ngram_range: tuple[int, int] = (1, 1),
        min_df: int = 1,
        max_features: int | None = None,
        sublinear_tf: bool = True,
    ):
        if analyzer not in {"word", "char_wb"}:
            raise ValueError(f"Unsupported analyzer: {analyzer}")
        self.analyzer = analyzer
        self.ngram_range = ngram_range
        self.min_df = max(1, int(min_df))
        self.max_features = max_features
        self.sublinear_tf = sublinear_tf
        self.vocabulary_: dict[str, int] = {}
        self.idf_: np.ndarray = np.empty(0, dtype=float)

    @property
    def dimension(self) -> int:
        return len(self.vocabulary_)

    def fit(self, texts: list[str]) -> ManualTfidfEncoder:
        document_frequency: Counter[str] = Counter()
        total_frequency: Counter[str] = Counter()
        for text in texts:
            terms = self._terms(text)
            if not terms:
                continue
            counts = Counter(terms)
            total_frequency.update(counts)
            document_frequency.update(counts.keys())

        stats = [
            (
                term,
                _TermStats(
                    document_frequency=document_frequency[term],
                    total_frequency=total_frequency[term],
                ),
            )
            for term in document_frequency
            if document_frequency[term] >= self.min_df
        ]
        if self.max_features is not None:
            stats = sorted(
                stats,
                key=lambda item: (-item[1].total_frequency, item[0]),
            )[: self.max_features]
        terms = sorted(term for term, _ in stats)
        self.vocabulary_ = {term: index for index, term in enumerate(terms)}

        document_count = max(1, len(texts))
        self.idf_ = np.asarray(
            [
                math.log(
                    (1.0 + document_count)
                    / (1.0 + document_frequency[term])
                )
                + 1.0
                for term in terms
            ],
            dtype=float,
        )
        return self

    def transform_sparse(self, texts: list[str]) -> list[dict[int, float]]:
        rows = []
        for text in texts:
            counts = Counter(
                index
                for term in self._terms(text)
                if (index := self.vocabulary_.get(term)) is not None
            )
            weighted: dict[int, float] = {}
            for index, count in counts.items():
                term_frequency = 1.0 + math.log(count) if self.sublinear_tf else float(count)
                weighted[index] = term_frequency * float(self.idf_[index])
            rows.append(_normalize_sparse(weighted))
        return rows

    def transform(self, texts: list[str]) -> np.ndarray:
        matrix = np.zeros((len(texts), self.dimension), dtype=float)
        for row_index, row in enumerate(self.transform_sparse(texts)):
            for column_index, value in row.items():
                matrix[row_index, column_index] = value
        return matrix

    def _terms(self, text: str) -> list[str]:
        return generate_terms(
            text,
            analyzer=self.analyzer,
            ngram_range=self.ngram_range,
        )


class ManualTextFeatureCombiner:
    def __init__(self, parts: list[tuple[str, ManualTfidfEncoder]]):
        if not parts:
            raise ValueError("ManualTextFeatureCombiner needs at least one part")
        self.parts = parts
        self.offsets_: dict[str, int] = {}
        self.dimension = 0

    def fit(self, texts: list[str]) -> ManualTextFeatureCombiner:
        offset = 0
        self.offsets_ = {}
        for name, vectorizer in self.parts:
            vectorizer.fit(texts)
            self.offsets_[name] = offset
            offset += vectorizer.dimension
        self.dimension = offset
        return self

    def transform_sparse(self, texts: list[str]) -> list[dict[int, float]]:
        rows = [dict() for _ in texts]
        for name, vectorizer in self.parts:
            offset = self.offsets_[name]
            for row, part_row in zip(
                rows,
                vectorizer.transform_sparse(texts),
                strict=True,
            ):
                for index, value in part_row.items():
                    row[offset + index] = value
        return rows

    def transform(self, texts: list[str]) -> np.ndarray:
        matrix = np.zeros((len(texts), self.dimension), dtype=float)
        for row_index, row in enumerate(self.transform_sparse(texts)):
            for column_index, value in row.items():
                matrix[row_index, column_index] = value
        return matrix


class ManualHashingTfidfEncoder:
    def __init__(
        self,
        *,
        n_features: int,
        analyzer: str = "word",
        ngram_range: tuple[int, int] = (1, 2),
        min_df: int = 1,
        sublinear_tf: bool = True,
    ):
        if n_features <= 0:
            raise ValueError("n_features must be positive")
        self.n_features = int(n_features)
        self.analyzer = analyzer
        self.ngram_range = ngram_range
        self.min_df = max(1, int(min_df))
        self.sublinear_tf = sublinear_tf
        self.idf_: dict[str, float] = {}

    @property
    def dimension(self) -> int:
        return self.n_features

    def fit(self, texts: list[str]) -> ManualHashingTfidfEncoder:
        document_frequency: Counter[str] = Counter()
        for text in texts:
            terms = set(
                generate_terms(
                    text,
                    analyzer=self.analyzer,
                    ngram_range=self.ngram_range,
                )
            )
            document_frequency.update(terms)

        document_count = max(1, len(texts))
        self.idf_ = {
            term: math.log(
                (1.0 + document_count)
                / (1.0 + frequency)
            )
            + 1.0
            for term, frequency in document_frequency.items()
            if frequency >= self.min_df
        }
        return self

    def transform(self, texts: list[str]) -> np.ndarray:
        matrix = np.zeros((len(texts), self.n_features), dtype=float)
        for row_index, text in enumerate(texts):
            counts = Counter(
                term
                for term in generate_terms(
                    text,
                    analyzer=self.analyzer,
                    ngram_range=self.ngram_range,
                )
                if term in self.idf_
            )
            for term, count in counts.items():
                term_frequency = 1.0 + math.log(count) if self.sublinear_tf else float(count)
                matrix[row_index, _stable_bucket(term, self.n_features)] += (
                    term_frequency * self.idf_[term]
                )
        return l2_normalize_rows(matrix)


def generate_terms(
    text: str,
    *,
    analyzer: str,
    ngram_range: tuple[int, int],
) -> list[str]:
    normalized = normalize_semantic_text(text)
    if not normalized:
        return []
    if analyzer == "word":
        return _word_ngrams(normalized.split(), ngram_range)
    if analyzer == "char_wb":
        return _char_wb_ngrams(normalized.split(), ngram_range)
    raise ValueError(f"Unsupported analyzer: {analyzer}")


def _word_ngrams(
    tokens: list[str],
    ngram_range: tuple[int, int],
) -> list[str]:
    minimum, maximum = ngram_range
    terms = []
    for size in range(minimum, maximum + 1):
        if size <= 0 or size > len(tokens):
            continue
        terms.extend(
            " ".join(tokens[index : index + size])
            for index in range(len(tokens) - size + 1)
        )
    return terms


def _char_wb_ngrams(
    tokens: list[str],
    ngram_range: tuple[int, int],
) -> list[str]:
    minimum, maximum = ngram_range
    terms = []
    for token in tokens:
        padded = f" {token} "
        for size in range(minimum, maximum + 1):
            if size <= 0 or size > len(padded):
                continue
            terms.extend(
                padded[index : index + size]
                for index in range(len(padded) - size + 1)
            )
    return terms


def _normalize_sparse(row: dict[int, float]) -> dict[int, float]:
    norm = math.sqrt(sum(value * value for value in row.values()))
    if not norm:
        return row
    return {index: value / norm for index, value in row.items()}


def _stable_bucket(term: str, n_features: int) -> int:
    digest = hashlib.blake2b(term.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % n_features
