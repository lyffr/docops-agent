from __future__ import annotations

import math
from collections import Counter

from .models import DocumentChunk, SearchHit
from .tokenization import character_ngrams, tokenize


class HybridRetriever:
    """Dependency-free hybrid baseline: BM25 plus character n-gram similarity."""

    def __init__(self, sparse_weight: float = 0.72) -> None:
        if not 0 <= sparse_weight <= 1:
            raise ValueError("sparse_weight must be between 0 and 1")
        self.sparse_weight = sparse_weight
        self.chunks: list[DocumentChunk] = []
        self._term_counts: list[Counter[str]] = []
        self._doc_freq: Counter[str] = Counter()
        self._lengths: list[int] = []
        self._ngrams: list[set[str]] = []

    def index(self, chunks: list[DocumentChunk]) -> None:
        self.chunks = list(chunks)
        self._term_counts = [Counter(tokenize(chunk.content)) for chunk in chunks]
        self._lengths = [sum(counts.values()) for counts in self._term_counts]
        self._doc_freq = Counter()
        for counts in self._term_counts:
            self._doc_freq.update(counts.keys())
        self._ngrams = [character_ngrams(chunk.content) for chunk in chunks]

    def _bm25(self, query_tokens: list[str], index: int) -> float:
        if not self.chunks:
            return 0.0
        counts = self._term_counts[index]
        doc_length = self._lengths[index]
        average_length = sum(self._lengths) / max(len(self._lengths), 1)
        score = 0.0
        k1, b = 1.5, 0.75
        for token in set(query_tokens):
            frequency = counts[token]
            if not frequency:
                continue
            document_frequency = self._doc_freq[token]
            idf = math.log(
                1
                + (len(self.chunks) - document_frequency + 0.5)
                / (document_frequency + 0.5)
            )
            denominator = frequency + k1 * (1 - b + b * doc_length / max(average_length, 1))
            score += idf * (frequency * (k1 + 1)) / denominator
        return score

    @staticmethod
    def _jaccard(left: set[str], right: set[str]) -> float:
        union = left | right
        return len(left & right) / len(union) if union else 0.0

    def search(self, query: str, top_k: int = 4) -> list[SearchHit]:
        if top_k <= 0 or not self.chunks:
            return []
        query_tokens = tokenize(query)
        query_ngrams = character_ngrams(query)
        sparse_raw = [self._bm25(query_tokens, index) for index in range(len(self.chunks))]
        sparse_max = max(sparse_raw, default=0.0)
        unique_query_tokens = set(query_tokens)
        unseen_idf = math.log(1 + (len(self.chunks) + 0.5) / 0.5)
        total_query_weight = sum(
            math.log(
                1
                + (len(self.chunks) - self._doc_freq[token] + 0.5)
                / (self._doc_freq[token] + 0.5)
            )
            if self._doc_freq[token]
            else unseen_idf
            for token in unique_query_tokens
        )
        hits: list[SearchHit] = []
        for index, chunk in enumerate(self.chunks):
            sparse = sparse_raw[index] / sparse_max if sparse_max else 0.0
            dense = self._jaccard(query_ngrams, self._ngrams[index])
            matched_query_weight = sum(
                math.log(
                    1
                    + (len(self.chunks) - self._doc_freq[token] + 0.5)
                    / (self._doc_freq[token] + 0.5)
                )
                for token in unique_query_tokens
                if token in self._term_counts[index]
            )
            coverage = matched_query_weight / total_query_weight if total_query_weight else 0.0
            combined = self.sparse_weight * sparse * coverage + (1 - self.sparse_weight) * dense
            if combined > 0:
                hits.append(
                    SearchHit(
                        chunk=chunk,
                        score=round(combined, 6),
                        sparse_score=round(sparse, 6),
                        dense_score=round(dense, 6),
                    )
                )
        return sorted(hits, key=lambda hit: hit.score, reverse=True)[:top_k]
