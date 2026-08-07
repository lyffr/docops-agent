import unittest

from docops_agent.models import ParsedSection
from docops_agent.store import KnowledgeBase, TicketStore


class KnowledgeBaseTests(unittest.TestCase):
    def test_empty_replacement_does_not_remove_an_existing_document(self) -> None:
        knowledge_base = KnowledgeBase()
        original = knowledge_base.add_document(
            "policy",
            "员工制度",
            [ParsedSection(text="员工每年享有十天带薪年假。", page=1)],
        )

        with self.assertRaisesRegex(ValueError, "没有可建立索引的文本"):
            knowledge_base.add_document("policy", "员工制度", [ParsedSection(text="   ")])

        self.assertEqual(knowledge_base.chunks, original)
        self.assertEqual(
            knowledge_base.retriever.search("十天年假", top_k=1)[0].chunk.id,
            original[0].id,
        )

    def test_documents_can_be_listed_reindexed_and_deleted(self) -> None:
        knowledge_base = KnowledgeBase()
        original = knowledge_base.add_document(
            "policy",
            "员工制度",
            [ParsedSection(text="员工每年享有十天带薪年假。", page=3)],
        )

        summary = knowledge_base.documents[0]
        self.assertEqual(summary.document_id, "policy")
        self.assertEqual(summary.sections, 1)
        self.assertEqual(summary.chunks, 1)
        self.assertEqual(summary.pages, 1)
        self.assertEqual(knowledge_base.reindex_document("policy"), original)
        self.assertTrue(knowledge_base.delete_document("policy"))
        self.assertFalse(knowledge_base.delete_document("policy"))
        self.assertEqual(knowledge_base.documents, [])
        self.assertEqual(knowledge_base.retriever.search("年假"), [])


class TicketStoreTests(unittest.TestCase):
    def test_invalid_priority_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "ticket priority"):
            TicketStore().create("电脑故障", "无法开机", priority="critical")


if __name__ == "__main__":
    unittest.main()
