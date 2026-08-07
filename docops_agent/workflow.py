from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Any
from uuid import uuid4

from .models import Approval, AuditEvent, Ticket
from .persistence import Repository
from .store import TicketStore


class ApprovalError(RuntimeError):
    pass


class ApprovalNotFoundError(ApprovalError):
    pass


class ApprovalConflictError(ApprovalError):
    pass


class ApprovalExpiredError(ApprovalError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


class ApprovalStore:
    def __init__(
        self,
        tickets: TicketStore,
        repository: Repository | None = None,
        ttl_seconds: int = 900,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("approval ttl_seconds must be greater than zero")
        self.tickets = tickets
        self.repository = repository
        self.ttl_seconds = ttl_seconds
        stored = repository.load_approvals() if repository is not None else []
        self._approvals: dict[str, Approval] = {approval.id: approval for approval in stored}
        self._lock = RLock()

    def request_ticket(
        self,
        title: str,
        description: str,
        requested_by: str,
        priority: str = "medium",
    ) -> Approval:
        requested_at = _now()
        approval = Approval(
            id=f"APR-{uuid4().hex[:12].upper()}",
            action_type="create_ticket",
            title=title,
            description=description,
            priority=priority,
            requested_by=requested_by,
            requested_at=_timestamp(requested_at),
            expires_at=_timestamp(requested_at + timedelta(seconds=self.ttl_seconds)),
        )
        with self._lock:
            if self.repository is not None:
                self.repository.save_approval(approval)
            self._approvals[approval.id] = approval
        return approval

    def _require_pending(self, approval_id: str) -> Approval:
        approval = self._approvals.get(approval_id)
        if approval is None:
            raise ApprovalNotFoundError("approval not found")
        if approval.status != "pending":
            raise ApprovalConflictError(f"approval is already {approval.status}")
        if _now() >= datetime.fromisoformat(approval.expires_at):
            expired = replace(
                approval,
                status="expired",
                resolved_at=_timestamp(_now()),
            )
            if self.repository is not None and not self.repository.finalize_approval(expired):
                raise ApprovalConflictError("approval state changed concurrently")
            self._approvals[approval.id] = expired
            raise ApprovalExpiredError("approval has expired")
        return approval

    def approve(self, approval_id: str, resolved_by: str) -> tuple[Approval, Ticket]:
        with self._lock:
            approval = self._require_pending(approval_id)
            ticket = Ticket(
                title=approval.title,
                description=approval.description,
                priority=approval.priority,
            )
            approved = replace(
                approval,
                status="approved",
                resolved_by=resolved_by,
                resolved_at=_timestamp(_now()),
                ticket_id=ticket.id,
            )
            if self.repository is not None:
                if not self.repository.finalize_approval(approved, ticket):
                    raise ApprovalConflictError("approval state changed concurrently")
            self.tickets.add(ticket, persist=False)
            self._approvals[approval.id] = approved
            return approved, ticket

    def reject(self, approval_id: str, resolved_by: str) -> Approval:
        with self._lock:
            approval = self._require_pending(approval_id)
            rejected = replace(
                approval,
                status="rejected",
                resolved_by=resolved_by,
                resolved_at=_timestamp(_now()),
            )
            if self.repository is not None and not self.repository.finalize_approval(rejected):
                raise ApprovalConflictError("approval state changed concurrently")
            self._approvals[approval.id] = rejected
            return rejected

    def get(self, approval_id: str) -> Approval | None:
        with self._lock:
            approval = self._approvals.get(approval_id)
            if approval is None:
                return None
            if approval.status == "pending":
                try:
                    self._require_pending(approval_id)
                except ApprovalExpiredError:
                    pass
            return self._approvals[approval_id]

    def list(self, status: str | None = None) -> list[Approval]:
        with self._lock:
            for approval_id in list(self._approvals):
                self.get(approval_id)
            approvals = list(reversed(self._approvals.values()))
            return [
                approval for approval in approvals if status is None or approval.status == status
            ]


class AuditStore:
    def __init__(self, repository: Repository | None = None) -> None:
        self.repository = repository
        stored = repository.load_audit_events(limit=1000) if repository is not None else []
        self._events: list[AuditEvent] = list(reversed(stored))
        self._lock = RLock()

    def record(
        self,
        event_type: str,
        actor: str,
        resource_type: str,
        resource_id: str,
        details: dict[str, Any] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            id=f"AUD-{uuid4().hex[:16].upper()}",
            event_type=event_type,
            actor=actor,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            created_at=_timestamp(_now()),
        )
        with self._lock:
            if self.repository is not None:
                self.repository.save_audit_event(event)
            self._events.append(event)
            if len(self._events) > 1000:
                self._events = self._events[-1000:]
        return event

    def list(self, limit: int = 100) -> list[AuditEvent]:
        limit = min(max(limit, 1), 1000)
        with self._lock:
            return list(reversed(self._events[-limit:]))
