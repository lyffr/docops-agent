import unittest

from docops_agent.models import ParsedSection
from docops_agent.store import KnowledgeBase


class RetrievalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.knowledge_base = KnowledgeBase()
        self.knowledge_base.add_document(
            "policy",
            "员工制度",
            [
                ParsedSection(text="员工每年享有十天带薪年假。", page=1),
                ParsedSection(text="办公电脑故障请创建 IT 支持工单。", page=2),
            ],
        )

    def test_relevant_chunk_ranks_first(self) -> None:
        hits = self.knowledge_base.retriever.search("年假有多少天", top_k=1)
        self.assertEqual(len(hits), 1)
        self.assertIn("十天", hits[0].chunk.content)

    def test_unknown_query_returns_no_hits(self) -> None:
        hits = self.knowledge_base.retriever.search("量子火箭发动机", top_k=3)
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()

