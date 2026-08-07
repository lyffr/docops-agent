from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


@dataclass(slots=True)
class ParsedSection:
    text: str
    page: int | None = None


@dataclass(slots=True)
class DocumentRecord:
    document_id: str
    title: str
    sections: list[ParsedSection]
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class DocumentSummary:
    document_id: str
    title: str
    sections: int
    chunks: int
    pages: int
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DocumentChunk:
    id: str
    document_id: str
    title: str
    content: str
    page: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SearchHit:
    chunk: DocumentChunk
    score: float
    sparse_score: float
    dense_score: float


@dataclass(slots=True)
class Citation:
    chunk_id: str
    document_id: str
    title: str
    page: int | None
    quote: str
    score: float


@dataclass(slots=True)
class Answer:
    question: str
    content: str
    citations: list[Citation]
    confidence: float
    abstained: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Ticket:
    title: str
    description: str
    priority: str = "medium"
    id: str = field(default_factory=lambda: f"TKT-{uuid4().hex[:8].upper()}")
    status: str = "open"
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Approval:
    id: str
    action_type: str
    title: str
    description: str
    priority: str
    requested_by: str
    requested_at: str
    expires_at: str
    status: str = "pending"
    resolved_by: str | None = None
    resolved_at: str | None = None
    ticket_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AuditEvent:
    id: str
    event_type: str
    actor: str
    resource_type: str
    resource_id: str
    details: dict[str, Any]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AgentResult:
    kind: str
    message: str
    requires_approval: bool = False
    answer: Answer | None = None
    ticket: Ticket | None = None
    approval: Approval | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return payload
