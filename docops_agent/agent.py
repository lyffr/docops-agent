from __future__ import annotations

import re

from .models import AgentResult
from .rag import RAGService
from .store import TicketStore
from .workflow import ApprovalStore, AuditStore

CREATE_TICKET_PATTERNS = (
    "创建工单",
    "新建工单",
    "提交工单",
    "报修",
    "create ticket",
)


class DocOpsAgent:
    def __init__(
        self,
        rag: RAGService,
        tickets: TicketStore | None = None,
        approvals: ApprovalStore | None = None,
        audit: AuditStore | None = None,
        approval_ttl_seconds: int = 900,
    ) -> None:
        self.rag = rag
        self.tickets = tickets if tickets is not None else TicketStore()
        self.approvals = (
            approvals
            if approvals is not None
            else ApprovalStore(
                self.tickets,
                repository=self.tickets.repository,
                ttl_seconds=approval_ttl_seconds,
            )
        )
        self.audit = audit if audit is not None else AuditStore(repository=self.tickets.repository)

    @staticmethod
    def _is_ticket_request(message: str) -> bool:
        lowered = message.lower()
        return any(pattern in lowered for pattern in CREATE_TICKET_PATTERNS)

    @staticmethod
    def _ticket_title(message: str) -> str:
        cleaned = message
        for pattern in CREATE_TICKET_PATTERNS:
            cleaned = re.sub(re.escape(pattern), "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip("：:，,。 !！")
        return cleaned[:48] or "用户提交的支持请求"

    def run(self, message: str, actor: str = "anonymous") -> AgentResult:
        message = message.strip()
        if not message:
            raise ValueError("message cannot be empty")
        if self._is_ticket_request(message):
            title = self._ticket_title(message)
            approval = self.approvals.request_ticket(
                title=title,
                description=message,
                requested_by=actor,
            )
            self.audit.record(
                "approval.requested",
                actor,
                "approval",
                approval.id,
                {"action_type": approval.action_type},
            )
            return AgentResult(
                kind="approval_required",
                message=f"即将创建工单“{title}”。请确认后执行。",
                requires_approval=True,
                approval=approval,
            )

        answer = self.rag.answer(message)
        self.audit.record(
            "query.completed",
            actor,
            "query",
            "-",
            {"abstained": answer.abstained, "citations": len(answer.citations)},
        )
        return AgentResult(kind="answer", message=answer.content, answer=answer)

    def approve(self, approval_id: str, actor: str) -> AgentResult:
        approval, ticket = self.approvals.approve(approval_id, actor)
        self.audit.record(
            "approval.approved",
            actor,
            "approval",
            approval.id,
            {"ticket_id": ticket.id},
        )
        return AgentResult(
            kind="ticket_created",
            message=f"工单 {ticket.id} 已创建。",
            ticket=ticket,
            approval=approval,
        )

    def reject(self, approval_id: str, actor: str) -> AgentResult:
        approval = self.approvals.reject(approval_id, actor)
        self.audit.record(
            "approval.rejected",
            actor,
            "approval",
            approval.id,
        )
        return AgentResult(
            kind="approval_rejected",
            message="操作已拒绝。",
            approval=approval,
        )
