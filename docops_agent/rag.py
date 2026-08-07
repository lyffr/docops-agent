from __future__ import annotations

from .generation import ExtractiveGenerator, Generator
from .models import Answer, Citation
from .store import KnowledgeBase


class RAGService:
    def __init__(
        self,
        knowledge_base: KnowledgeBase,
        generator: Generator | None = None,
        top_k: int = 4,
        min_evidence_score: float = 0.08,
    ) -> None:
        if top_k <= 0:
            raise ValueError("top_k must be greater than zero")
        if not 0 <= min_evidence_score <= 1:
            raise ValueError("min_evidence_score must be between 0 and 1")
        self.knowledge_base = knowledge_base
        self.generator = generator if generator is not None else ExtractiveGenerator()
        self.top_k = top_k
        self.min_evidence_score = min_evidence_score

    def answer(self, question: str) -> Answer:
        question = question.strip()
        if not question:
            raise ValueError("question cannot be empty")
        hits = self.knowledge_base.retriever.search(question, top_k=self.top_k)
        if not hits or hits[0].score < self.min_evidence_score:
            return Answer(
                question=question,
                content="现有文档中没有足够证据回答该问题。",
                citations=[],
                confidence=round(hits[0].score if hits else 0.0, 4),
                abstained=True,
            )

        citations = [
            Citation(
                chunk_id=hit.chunk.id,
                document_id=hit.chunk.document_id,
                title=hit.chunk.title,
                page=hit.chunk.page,
                quote=hit.chunk.content[:220],
                score=hit.score,
            )
            for hit in hits
        ]
        return Answer(
            question=question,
            content=self.generator.generate(question, hits),
            citations=citations,
            confidence=round(hits[0].score, 4),
            abstained=False,
        )
