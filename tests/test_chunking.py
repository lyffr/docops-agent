import unittest

from docops_agent.chunking import chunk_sections, split_text
from docops_agent.models import ParsedSection


class ChunkingTests(unittest.TestCase):
    def test_long_text_is_split_with_limit(self) -> None:
        chunks = split_text("第一段。" * 200, max_chars=120, overlap_chars=20)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 120 for chunk in chunks))

    def test_chunk_ids_are_deterministic(self) -> None:
        sections = [ParsedSection(text="稳定的测试内容", page=2)]
        first = chunk_sections("doc", "标题", sections)
        second = chunk_sections("doc", "标题", sections)
        self.assertEqual(first[0].id, second[0].id)
        self.assertEqual(first[0].page, 2)


if __name__ == "__main__":
    unittest.main()

