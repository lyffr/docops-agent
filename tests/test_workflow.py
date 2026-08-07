import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from docops_agent.store import TicketStore
from docops_agent.workflow import ApprovalExpiredError, ApprovalStore, AuditStore


class ApprovalStoreTests(unittest.TestCase):
    def test_expired_approval_cannot_create_a_ticket(self) -> None:
        tickets = TicketStore()
        approvals = ApprovalStore(tickets, ttl_seconds=1)
        approval = approvals.request_ticket("电脑故障", "电脑无法开机", "requester")
        after_expiry = datetime.fromisoformat(approval.expires_at) + timedelta(seconds=1)

        with patch("docops_agent.workflow._now", return_value=after_expiry):
            with self.assertRaises(ApprovalExpiredError):
                approvals.approve(approval.id, "operator")

        self.assertEqual(approvals.get(approval.id).status, "expired")
        self.assertEqual(tickets.list(), [])


class AuditStoreTests(unittest.TestCase):
    def test_events_are_returned_newest_first(self) -> None:
        audit = AuditStore()
        first = audit.record("first", "actor", "document", "one")
        second = audit.record("second", "actor", "document", "two")

        self.assertEqual([event.id for event in audit.list()], [second.id, first.id])
        self.assertEqual(audit.list(limit=1)[0].id, second.id)


if __name__ == "__main__":
    unittest.main()
