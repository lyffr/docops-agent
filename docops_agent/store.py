from __future__ import annotations

from threading import RLock

from .chunking import chunk_sections
from .models import DocumentChunk, ParsedSection, Ticket
from .retrieval import HybridRetriever


class KnowledgeBase:
    def __init__(self, retriever: HybridRetriever | None = None) -> None:
        self.retriever = retriever or HybridRetriever()
        self._chunks: dict[str, DocumentChunk] = {}
        self._lock = RLock()

    @property
    def chunks(self) -> list[DocumentChunk]:
        with self._lock:
            return list(self._chunks.values())

    def add_document(
        self, document_id: str, title: str, sections: list[ParsedSection]
    ) -> list[DocumentChunk]:
        if not document_id.strip():
            raise ValueError("document_id cannot be empty")
        if not title.strip():
            raise ValueError("title cannot be empty")
        chunks = chunk_sections(document_id, title, sections)
        if not chunks:
            raise ValueError("文档中没有可建立索引的文本。")
        with self._lock:
            updated_chunks = {
                key: value
                for key, value in self._chunks.items()
                if value.document_id != document_id
            }
            updated_chunks.update({chunk.id: chunk for chunk in chunks})
            self.retriever.index(list(updated_chunks.values()))
            self._chunks = updated_chunks
        return chunks


class TicketStore:
    def __init__(self) -> None:
        self._tickets: dict[str, Ticket] = {}
        self._lock = RLock()

    def create(self, title: str, description: str, priority: str = "medium") -> Ticket:
        title = title.strip()
        description = description.strip()
        priority = priority.strip().lower()
        if not title:
            raise ValueError("ticket title cannot be empty")
        if not description:
            raise ValueError("ticket description cannot be empty")
        if priority not in {"low", "medium", "high", "urgent"}:
            raise ValueError("ticket priority must be low, medium, high, or urgent")
        ticket = Ticket(title=title, description=description, priority=priority)
        with self._lock:
            self._tickets[ticket.id] = ticket
        return ticket

    def list(self) -> list[Ticket]:
        with self._lock:
            return list(reversed(self._tickets.values()))
