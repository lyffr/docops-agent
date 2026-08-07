from __future__ import annotations

import sqlite3
from pathlib import Path
from threading import RLock
from typing import Protocol

from .models import DocumentRecord, ParsedSection, Ticket

SCHEMA_VERSION = 1


class Repository(Protocol):
    def save_document(self, record: DocumentRecord) -> None: ...

    def load_documents(self) -> list[DocumentRecord]: ...

    def delete_document(self, document_id: str) -> bool: ...

    def save_ticket(self, ticket: Ticket) -> None: ...

    def load_tickets(self) -> list[Ticket]: ...


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
        self._initialize()

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

    def close(self) -> None:
        with self._lock:
            self._connection.close()
