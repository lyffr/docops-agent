import unittest

from docops_agent.agent import DocOpsAgent
from docops_agent.rag import RAGService
from docops_agent.store import KnowledgeBase


class AgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = DocOpsAgent(RAGService(KnowledgeBase()))

    def test_ticket_creation_requires_approval(self) -> None:
        result = self.agent.run("创建工单：电脑无法开机")
        self.assertTrue(result.requires_approval)
        self.assertEqual(self.agent.tickets.list(), [])

    def test_approved_ticket_is_created(self) -> None:
        result = self.agent.run("创建工单：电脑无法开机", approved=True)
        self.assertFalse(result.requires_approval)
        self.assertIsNotNone(result.ticket)
        self.assertEqual(len(self.agent.tickets.list()), 1)


if __name__ == "__main__":
    unittest.main()

