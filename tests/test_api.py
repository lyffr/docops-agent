import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from docops_agent.api import (
    QueryRequest,
    TextDocumentRequest,
    _document_id,
    _safe_filename,
    _validate_document_size,
)


class ApiHelpersTests(unittest.TestCase):
    def test_uploaded_paths_are_reduced_to_a_filename(self) -> None:
        self.assertEqual(_safe_filename(r"C:\fakepath\manual.pdf"), "manual.pdf")
        self.assertEqual(_safe_filename("../../manual.pdf"), "manual.pdf")

    def test_non_ascii_filenames_get_distinct_stable_ids(self) -> None:
        first = _document_id("员工手册.pdf")
        second = _document_id("费用制度.pdf")

        self.assertEqual(first, _document_id("员工手册.pdf"))
        self.assertNotEqual(first, second)
        self.assertTrue(first.startswith("upload-"))

    def test_user_input_is_trimmed_and_whitespace_only_input_is_rejected(self) -> None:
        self.assertEqual(QueryRequest(question="  年假  ").question, "年假")

        with self.assertRaises(ValueError):
            QueryRequest(question="   ")

    def test_document_ids_are_safe_for_url_paths(self) -> None:
        request = TextDocumentRequest(document_id="policy_2026", title="制度", text="正文")
        self.assertEqual(request.document_id, "policy_2026")

        with self.assertRaises(ValueError):
            TextDocumentRequest(document_id="部门/制度", title="制度", text="正文")

    def test_document_size_limit_is_enforced(self) -> None:
        with patch("docops_agent.api.settings", SimpleNamespace(max_upload_bytes=3)):
            _validate_document_size(b"123")
            with self.assertRaises(HTTPException) as context:
                _validate_document_size(b"1234")

        self.assertEqual(context.exception.status_code, 413)


if __name__ == "__main__":
    unittest.main()
