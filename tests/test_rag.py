import unittest

from docops_agent.models import ParsedSection
from docops_agent.rag import RAGService
from docops_agent.store import KnowledgeBase


class RAGTests(unittest.TestCase):
    def setUp(self) -> None:
        knowledge_base = KnowledgeBase()
        knowledge_base.add_document(
            "handbook",
            "员工手册",
            [ParsedSection(text="员工应在费用发生后的三十个自然日内提交报销。", page=7)],
        )
        self.rag = RAGService(knowledge_base, min_evidence_score=0.08)

    def test_answer_contains_citation(self) -> None:
        answer = self.rag.answer("报销最晚什么时候提交？")
        self.assertFalse(answer.abstained)
        self.assertEqual(answer.citations[0].page, 7)
        self.assertIn("三十个自然日", answer.content)

    def test_abstains_without_evidence(self) -> None:
        answer = self.rag.answer("今天股票涨了多少？")
        self.assertTrue(answer.abstained)
        self.assertEqual(answer.citations, [])


if __name__ == "__main__":
    unittest.main()

