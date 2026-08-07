from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock

from .chunking import chunk_sections
from .models import DocumentChunk, DocumentRecord, DocumentSummary, ParsedSection, Ticket
from .persistence import Repository
from .retrieval import HybridRetriever


class KnowledgeBase:
    def __init__(
        self,
        retriever: HybridRetriever | None = None,
        repository: Repository | None = None,
    ) -> None:
        self.retriever = retriever if retriever is not None else HybridRetriever()
        self.repository = repository
        self._documents: dict[str, DocumentRecord] = {}
        self._chunks: dict[str, DocumentChunk] = {}
        self._lock = RLock()
        if repository is not None:
            self._restore(repository.load_documents())

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def _restore(self, records: list[DocumentRecord]) -> None:
        restored_chunks: dict[str, DocumentChunk] = {}
        for record in records:
            chunks = chunk_sections(record.document_id, record.title, record.sections)
            restored_chunks.update({chunk.id: chunk for chunk in chunks})
        self._documents = {record.document_id: record for record in records}
        self._chunks = restored_chunks
        self.retriever.index(list(restored_chunks.values()))

    @property
    def chunks(self) -> list[DocumentChunk]:
        with self._lock:
            return list(self._chunks.values())

    @property
    def documents(self) -> list[DocumentSummary]:
        with self._lock:
            chunk_counts: dict[str, int] = {}
            for chunk in self._chunks.values():
                chunk_counts[chunk.document_id] = chunk_counts.get(chunk.document_id, 0) + 1
            summaries = [
                DocumentSummary(
                    document_id=record.document_id,
                    title=record.title,
                    sections=len(record.sections),
                    chunks=chunk_counts.get(record.document_id, 0),
                    pages=len(
                        {section.page for section in record.sections if section.page is not None}
                    ),
                    created_at=record.created_at,
                    updated_at=record.updated_at,
                )
                for record in self._documents.values()
            ]
        return sorted(summaries, key=lambda item: (item.updated_at, item.document_id), reverse=True)

    def has_document(self, document_id: str) -> bool:
        with self._lock:
            return document_id in self._documents

    def add_document(
        self, document_id: str, title: str, sections: list[ParsedSection]
    ) -> list[DocumentChunk]:
        document_id = document_id.strip()
        title = title.strip()
        if not document_id:
            raise ValueError("document_id cannot be empty")
        if not title:
            raise ValueError("title cannot be empty")
        stored_sections = [
            ParsedSection(text=section.text, page=section.page) for section in sections
        ]
        chunks = chunk_sections(document_id, title, stored_sections)
        if not chunks:
            raise ValueError("文档中没有可建立索引的文本。")
        with self._lock:
            now = self._now()
            existing = self._documents.get(document_id)
            record = DocumentRecord(
                document_id=document_id,
                title=title,
                sections=stored_sections,
                created_at=existing.created_at if existing is not None else now,
                updated_at=now,
            )
            updated_chunks = {
                key: value
                for key, value in self._chunks.items()
                if value.document_id != document_id
            }
            updated_chunks.update({chunk.id: chunk for chunk in chunks})
            if self.repository is not None:
                self.repository.save_document(record)
            self.retriever.index(list(updated_chunks.values()))
            self._documents[document_id] = record
            self._chunks = updated_chunks
        return chunks

    def delete_document(self, document_id: str) -> bool:
        document_id = document_id.strip()
        with self._lock:
            if document_id not in self._documents:
                return False
            updated_chunks = {
                key: value
                for key, value in self._chunks.items()
                if value.document_id != document_id
            }
            if self.repository is not None:
                self.repository.delete_document(document_id)
            self.retriever.index(list(updated_chunks.values()))
            del self._documents[document_id]
            self._chunks = updated_chunks
            return True

    def reindex_document(self, document_id: str) -> list[DocumentChunk] | None:
        document_id = document_id.strip()
        with self._lock:
            record = self._documents.get(document_id)
            if record is None:
                return None
            chunks = chunk_sections(record.document_id, record.title, record.sections)
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
    def __init__(self, repository: Repository | None = None) -> None:
        self.repository = repository
        stored_tickets = repository.load_tickets() if repository is not None else []
        self._tickets: dict[str, Ticket] = {ticket.id: ticket for ticket in stored_tickets}
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
            if self.repository is not None:
                self.repository.save_ticket(ticket)
            self._tickets[ticket.id] = ticket
        return ticket

    def list(self) -> list[Ticket]:
        with self._lock:
            return list(reversed(self._tickets.values()))
