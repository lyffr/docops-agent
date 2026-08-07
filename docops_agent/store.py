from __future__ import annotations

from .chunking import chunk_sections
from .models import DocumentChunk, ParsedSection, Ticket
from .retrieval import HybridRetriever


class KnowledgeBase:
    def __init__(self, retriever: HybridRetriever | None = None) -> None:
        self.retriever = retriever or HybridRetriever()
        self._chunks: dict[str, DocumentChunk] = {}

    @property
    def chunks(self) -> list[DocumentChunk]:
        return list(self._chunks.values())

    def add_document(
        self, document_id: str, title: str, sections: list[ParsedSection]
    ) -> list[DocumentChunk]:
        chunks = chunk_sections(document_id, title, sections)
        self._chunks = {
            key: value
            for key, value in self._chunks.items()
            if value.document_id != document_id
        }
        self._chunks.update({chunk.id: chunk for chunk in chunks})
        self.retriever.index(self.chunks)
        return chunks


class TicketStore:
    def __init__(self) -> None:
        self._tickets: dict[str, Ticket] = {}

    def create(self, title: str, description: str, priority: str = "medium") -> Ticket:
        ticket = Ticket(title=title, description=description, priority=priority)
        self._tickets[ticket.id] = ticket
        return ticket

    def list(self) -> list[Ticket]:
        return list(reversed(self._tickets.values()))

