from __future__ import annotations

import re

from .models import AgentResult
from .rag import RAGService
from .store import TicketStore

CREATE_TICKET_PATTERNS = (
    "创建工单",
    "新建工单",
    "提交工单",
    "报修",
    "create ticket",
)


class DocOpsAgent:
    def __init__(self, rag: RAGService, tickets: TicketStore | None = None) -> None:
        self.rag = rag
        self.tickets = tickets or TicketStore()

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

    def run(self, message: str, approved: bool = False) -> AgentResult:
        if self._is_ticket_request(message):
            title = self._ticket_title(message)
            if not approved:
                return AgentResult(
                    kind="approval_required",
                    message=f"即将创建工单“{title}”。请确认后执行。",
                    requires_approval=True,
                )
            ticket = self.tickets.create(title=title, description=message)
            return AgentResult(
                kind="ticket_created",
                message=f"工单 {ticket.id} 已创建。",
                ticket=ticket,
            )

        answer = self.rag.answer(message)
        return AgentResult(kind="answer", message=answer.content, answer=answer)

