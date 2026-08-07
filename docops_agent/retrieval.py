from __future__ import annotations

import math
from collections import Counter
from threading import RLock

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
        self._average_length = 0.0
        self._ngrams: list[set[str]] = []
        self._lock = RLock()

    def index(self, chunks: list[DocumentChunk]) -> None:
        indexed_chunks = list(chunks)
        term_counts = [Counter(tokenize(chunk.content)) for chunk in indexed_chunks]
        lengths = [sum(counts.values()) for counts in term_counts]
        doc_freq: Counter[str] = Counter()
        for counts in term_counts:
            doc_freq.update(counts.keys())
        ngrams = [character_ngrams(chunk.content) for chunk in indexed_chunks]

        with self._lock:
            self.chunks = indexed_chunks
            self._term_counts = term_counts
            self._lengths = lengths
            self._average_length = sum(lengths) / len(lengths) if lengths else 0.0
            self._doc_freq = doc_freq
            self._ngrams = ngrams

    def _idf(self, document_frequency: int) -> float:
        return math.log(
            1 + (len(self.chunks) - document_frequency + 0.5) / (document_frequency + 0.5)
        )

    def _bm25(self, query_tokens: list[str], index: int) -> float:
        if not self.chunks:
            return 0.0
        counts = self._term_counts[index]
        doc_length = self._lengths[index]
        score = 0.0
        k1, b = 1.5, 0.75
        for token in set(query_tokens):
            frequency = counts[token]
            if not frequency:
                continue
            document_frequency = self._doc_freq[token]
            idf = self._idf(document_frequency)
            denominator = frequency + k1 * (1 - b + b * doc_length / max(self._average_length, 1))
            score += idf * (frequency * (k1 + 1)) / denominator
        return score

    @staticmethod
    def _jaccard(left: set[str], right: set[str]) -> float:
        union = left | right
        return len(left & right) / len(union) if union else 0.0

    def search(self, query: str, top_k: int = 4) -> list[SearchHit]:
        with self._lock:
            if top_k <= 0 or not self.chunks:
                return []
            query_tokens = tokenize(query)
            query_ngrams = character_ngrams(query)
            if not query_tokens and not query_ngrams:
                return []

            sparse_raw = [self._bm25(query_tokens, index) for index in range(len(self.chunks))]
            sparse_max = max(sparse_raw, default=0.0)
            unique_query_tokens = set(query_tokens)
            total_query_weight = sum(
                self._idf(self._doc_freq[token]) for token in unique_query_tokens
            )
            hits: list[SearchHit] = []
            for index, chunk in enumerate(self.chunks):
                sparse = sparse_raw[index] / sparse_max if sparse_max else 0.0
                dense = self._jaccard(query_ngrams, self._ngrams[index])
                matched_query_weight = sum(
                    self._idf(self._doc_freq[token])
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
