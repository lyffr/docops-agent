import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from docops_agent.parsers import parse_document


class ParserTests(unittest.TestCase):
    def test_pdf_page_text_is_extracted_once(self) -> None:
        class Page:
            def __init__(self, text: str) -> None:
                self.text = text
                self.calls = 0

            def extract_text(self) -> str:
                self.calls += 1
                return self.text

        pages = [Page("第一页"), Page("   ")]
        fake_pypdf = SimpleNamespace(PdfReader=lambda _: SimpleNamespace(pages=pages))

        with patch.dict(sys.modules, {"pypdf": fake_pypdf}):
            sections = parse_document("manual.pdf", b"fake-pdf")

        self.assertEqual([section.text for section in sections], ["第一页"])
        self.assertEqual([page.calls for page in pages], [1, 1])


if __name__ == "__main__":
    unittest.main()
