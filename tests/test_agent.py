import unittest

from docops_agent.agent import DocOpsAgent
from docops_agent.rag import RAGService
from docops_agent.store import KnowledgeBase
from docops_agent.workflow import ApprovalConflictError


class AgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = DocOpsAgent(RAGService(KnowledgeBase()))

    def test_ticket_creation_requires_approval(self) -> None:
        result = self.agent.run("创建工单：电脑无法开机")
        self.assertTrue(result.requires_approval)
        self.assertEqual(self.agent.tickets.list(), [])

    def test_approved_ticket_is_created(self) -> None:
        pending = self.agent.run("创建工单：电脑无法开机", actor="requester")

        result = self.agent.approve(pending.approval.id, actor="operator")

        self.assertFalse(result.requires_approval)
        self.assertIsNotNone(result.ticket)
        self.assertEqual(len(self.agent.tickets.list()), 1)
        self.assertEqual(result.approval.status, "approved")
        self.assertEqual(result.approval.resolved_by, "operator")
        with self.assertRaises(ApprovalConflictError):
            self.agent.approve(pending.approval.id, actor="operator")

    def test_rejected_ticket_is_not_created(self) -> None:
        pending = self.agent.run("创建工单：电脑无法开机", actor="requester")

        result = self.agent.reject(pending.approval.id, actor="operator")

        self.assertEqual(result.approval.status, "rejected")
        self.assertEqual(self.agent.tickets.list(), [])

    def test_empty_message_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "message cannot be empty"):
            self.agent.run("   ")


if __name__ == "__main__":
    unittest.main()
