from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Protocol

from .models import Approval, AuditEvent, DocumentRecord, ParsedSection, Ticket

SCHEMA_VERSION = 2


class Repository(Protocol):
    def save_document(self, record: DocumentRecord) -> None: ...

    def load_documents(self) -> list[DocumentRecord]: ...

    def delete_document(self, document_id: str) -> bool: ...

    def save_ticket(self, ticket: Ticket) -> None: ...

    def load_tickets(self) -> list[Ticket]: ...

    def save_approval(self, approval: Approval) -> None: ...

    def load_approvals(self) -> list[Approval]: ...

    def finalize_approval(self, approval: Approval, ticket: Ticket | None = None) -> bool: ...

    def save_audit_event(self, event: AuditEvent) -> None: ...

    def load_audit_events(self, limit: int = 100) -> list[AuditEvent]: ...

    def ping(self) -> bool: ...

    def close(self) -> None: ...


class SQLiteRepository:
    """Thread-safe SQLite persistence for source documents and tickets."""

    def __init__(self, database_path: str) -> None:
        database_path = database_path.strip()
        if not database_path:
            raise ValueError("database_path cannot be empty")
        if database_path != ":memory:":
            Path(database_path).parent.mkdir(parents=True, exist_ok=True)

        self.database_path = database_path
        self._lock = RLock()
        self._connection = sqlite3.connect(
            database_path,
            timeout=10,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        try:
            self._initialize()
        except Exception:
            self._connection.close()
            raise

    def _initialize(self) -> None:
        with self._lock, self._connection:
            schema_version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            if schema_version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"Database schema version {schema_version} is newer than supported "
                    f"version {SCHEMA_VERSION}"
                )
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute("PRAGMA busy_timeout = 10000")
            if self.database_path != ":memory:":
                self._connection.execute("PRAGMA journal_mode = WAL")
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    document_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS document_sections (
                    document_id TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    page INTEGER,
                    text TEXT NOT NULL,
                    PRIMARY KEY (document_id, position),
                    FOREIGN KEY (document_id) REFERENCES documents(document_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS tickets (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket_id TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS approvals (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    approval_id TEXT NOT NULL UNIQUE,
                    action_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    requested_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    resolved_by TEXT,
                    resolved_at TEXT,
                    ticket_id TEXT
                );

                CREATE TABLE IF NOT EXISTS audit_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    resource_type TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_approvals_status
                ON approvals(status, expires_at);

                CREATE INDEX IF NOT EXISTS idx_audit_events_created_at
                ON audit_events(created_at);
                """
            )
            if schema_version < SCHEMA_VERSION:
                self._connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def save_document(self, record: DocumentRecord) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO documents (document_id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    title = excluded.title,
                    updated_at = excluded.updated_at
                """,
                (record.document_id, record.title, record.created_at, record.updated_at),
            )
            self._connection.execute(
                "DELETE FROM document_sections WHERE document_id = ?",
                (record.document_id,),
            )
            self._connection.executemany(
                """
                INSERT INTO document_sections (document_id, position, page, text)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (record.document_id, position, section.page, section.text)
                    for position, section in enumerate(record.sections)
                ],
            )

    def load_documents(self) -> list[DocumentRecord]:
        with self._lock:
            document_rows = self._connection.execute(
                """
                SELECT document_id, title, created_at, updated_at
                FROM documents
                ORDER BY created_at, document_id
                """
            ).fetchall()
            section_rows = self._connection.execute(
                """
                SELECT document_id, page, text
                FROM document_sections
                ORDER BY document_id, position
                """
            ).fetchall()

        sections_by_document: dict[str, list[ParsedSection]] = {}
        for row in section_rows:
            sections_by_document.setdefault(row["document_id"], []).append(
                ParsedSection(text=row["text"], page=row["page"])
            )
        return [
            DocumentRecord(
                document_id=row["document_id"],
                title=row["title"],
                sections=sections_by_document.get(row["document_id"], []),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in document_rows
        ]

    def delete_document(self, document_id: str) -> bool:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "DELETE FROM documents WHERE document_id = ?",
                (document_id,),
            )
            return cursor.rowcount > 0

    def save_ticket(self, ticket: Ticket) -> None:
        with self._lock, self._connection:
            self._insert_ticket(ticket)

    def _insert_ticket(self, ticket: Ticket) -> None:
        self._connection.execute(
            """
            INSERT INTO tickets (
                ticket_id, title, description, priority, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                ticket.id,
                ticket.title,
                ticket.description,
                ticket.priority,
                ticket.status,
                ticket.created_at,
            ),
        )

    def load_tickets(self) -> list[Ticket]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT ticket_id, title, description, priority, status, created_at
                FROM tickets
                ORDER BY sequence
                """
            ).fetchall()
        return [
            Ticket(
                id=row["ticket_id"],
                title=row["title"],
                description=row["description"],
                priority=row["priority"],
                status=row["status"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def save_approval(self, approval: Approval) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO approvals (
                    approval_id, action_type, title, description, priority,
                    requested_by, requested_at, expires_at, status,
                    resolved_by, resolved_at, ticket_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    approval.id,
                    approval.action_type,
                    approval.title,
                    approval.description,
                    approval.priority,
                    approval.requested_by,
                    approval.requested_at,
                    approval.expires_at,
                    approval.status,
                    approval.resolved_by,
                    approval.resolved_at,
                    approval.ticket_id,
                ),
            )

    def load_approvals(self) -> list[Approval]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT approval_id, action_type, title, description, priority,
                       requested_by, requested_at, expires_at, status,
                       resolved_by, resolved_at, ticket_id
                FROM approvals
                ORDER BY sequence
                """
            ).fetchall()
        return [
            Approval(
                id=row["approval_id"],
                action_type=row["action_type"],
                title=row["title"],
                description=row["description"],
                priority=row["priority"],
                requested_by=row["requested_by"],
                requested_at=row["requested_at"],
                expires_at=row["expires_at"],
                status=row["status"],
                resolved_by=row["resolved_by"],
                resolved_at=row["resolved_at"],
                ticket_id=row["ticket_id"],
            )
            for row in rows
        ]

    def finalize_approval(self, approval: Approval, ticket: Ticket | None = None) -> bool:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                UPDATE approvals
                SET status = ?, resolved_by = ?, resolved_at = ?, ticket_id = ?
                WHERE approval_id = ? AND status = 'pending'
                """,
                (
                    approval.status,
                    approval.resolved_by,
                    approval.resolved_at,
                    approval.ticket_id,
                    approval.id,
                ),
            )
            if cursor.rowcount != 1:
                return False
            if ticket is not None:
                self._insert_ticket(ticket)
            return True

    def save_audit_event(self, event: AuditEvent) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO audit_events (
                    event_id, event_type, actor, resource_type,
                    resource_id, details_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.event_type,
                    event.actor,
                    event.resource_type,
                    event.resource_id,
                    json.dumps(event.details, ensure_ascii=False, sort_keys=True),
                    event.created_at,
                ),
            )

    def load_audit_events(self, limit: int = 100) -> list[AuditEvent]:
        limit = min(max(limit, 1), 1000)
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT event_id, event_type, actor, resource_type,
                       resource_id, details_json, created_at
                FROM audit_events
                ORDER BY sequence DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            AuditEvent(
                id=row["event_id"],
                event_type=row["event_type"],
                actor=row["actor"],
                resource_type=row["resource_type"],
                resource_id=row["resource_id"],
                details=json.loads(row["details_json"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def ping(self) -> bool:
        with self._lock:
            return self._connection.execute("SELECT 1").fetchone()[0] == 1

    def close(self) -> None:
        with self._lock:
            self._connection.close()
