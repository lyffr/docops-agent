import tempfile
import unittest
from pathlib import Path

from docops_agent.models import ParsedSection
from docops_agent.persistence import SQLiteRepository
from docops_agent.store import KnowledgeBase, TicketStore


class SQLitePersistenceTests(unittest.TestCase):
    def test_documents_and_tickets_survive_repository_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = str(Path(directory) / "docops.db")
            first_repository = SQLiteRepository(database_path)
            first_knowledge_base = KnowledgeBase(repository=first_repository)
            first_tickets = TicketStore(first_repository)
            chunks = first_knowledge_base.add_document(
                "policy",
                "员工制度",
                [ParsedSection(text="员工每年享有十天带薪年假。", page=3)],
            )
            ticket = first_tickets.create("电脑故障", "办公电脑无法开机")
            first_repository.close()

            second_repository = SQLiteRepository(database_path)
            second_knowledge_base = KnowledgeBase(repository=second_repository)
            second_tickets = TicketStore(second_repository)

            self.assertEqual(second_knowledge_base.documents[0].document_id, "policy")
            self.assertEqual(
                second_knowledge_base.retriever.search("十天年假", top_k=1)[0].chunk.id,
                chunks[0].id,
            )
            self.assertEqual(second_tickets.list()[0].id, ticket.id)
            self.assertTrue(second_knowledge_base.delete_document("policy"))
            second_repository.close()

            third_repository = SQLiteRepository(database_path)
            third_knowledge_base = KnowledgeBase(repository=third_repository)
            third_tickets = TicketStore(third_repository)
            self.assertEqual(third_knowledge_base.documents, [])
            self.assertEqual(third_tickets.list()[0].id, ticket.id)
            third_repository.close()


if __name__ == "__main__":
    unittest.main()
