import sqlite3
import tempfile
import unittest
from pathlib import Path

from docops_agent.models import ParsedSection
from docops_agent.persistence import SQLiteRepository
from docops_agent.store import KnowledgeBase, TicketStore
from docops_agent.workflow import ApprovalStore, AuditStore


class SQLitePersistenceTests(unittest.TestCase):
    def test_version_one_database_is_migrated_and_newer_database_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = str(Path(directory) / "migration.db")
            connection = sqlite3.connect(database_path)
            connection.execute("PRAGMA user_version = 1")
            connection.close()

            repository = SQLiteRepository(database_path)
            repository.close()
            connection = sqlite3.connect(database_path)
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            connection.execute("PRAGMA user_version = 99")
            connection.close()

            self.assertEqual(version, 2)
            self.assertIn("approvals", tables)
            self.assertIn("audit_events", tables)
            with self.assertRaisesRegex(RuntimeError, "newer than supported"):
                SQLiteRepository(database_path)

    def test_documents_and_tickets_survive_repository_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = str(Path(directory) / "docops.db")
            first_repository = SQLiteRepository(database_path)
            first_knowledge_base = KnowledgeBase(repository=first_repository)
            first_tickets = TicketStore(first_repository)
            first_approvals = ApprovalStore(first_tickets, first_repository)
            first_audit = AuditStore(first_repository)
            chunks = first_knowledge_base.add_document(
                "policy",
                "员工制度",
                [ParsedSection(text="员工每年享有十天带薪年假。", page=3)],
            )
            approval = first_approvals.request_ticket(
                "电脑故障",
                "办公电脑无法开机",
                "requester",
            )
            approved, ticket = first_approvals.approve(approval.id, "operator")
            event = first_audit.record(
                "approval.approved",
                "operator",
                "approval",
                approved.id,
            )
            first_repository.close()

            second_repository = SQLiteRepository(database_path)
            second_knowledge_base = KnowledgeBase(repository=second_repository)
            second_tickets = TicketStore(second_repository)
            second_approvals = ApprovalStore(second_tickets, second_repository)
            second_audit = AuditStore(second_repository)

            self.assertEqual(second_knowledge_base.documents[0].document_id, "policy")
            self.assertEqual(
                second_knowledge_base.retriever.search("十天年假", top_k=1)[0].chunk.id,
                chunks[0].id,
            )
            self.assertEqual(second_tickets.list()[0].id, ticket.id)
            self.assertEqual(second_approvals.get(approval.id).status, "approved")
            self.assertEqual(second_audit.list()[0].id, event.id)
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
