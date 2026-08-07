import unittest

from docops_agent.generation import ExtractiveGenerator
from docops_agent.models import DocumentChunk, SearchHit


class ExtractiveGeneratorTests(unittest.TestCase):
    def test_overlapping_chunks_do_not_duplicate_the_same_sentence(self) -> None:
        sentence = "员工每年享有十天带薪年假。"
        hits = [
            SearchHit(
                chunk=DocumentChunk(
                    id=f"chunk-{index}",
                    document_id="handbook",
                    title="员工手册",
                    content=sentence,
                ),
                score=score,
                sparse_score=score,
                dense_score=0,
            )
            for index, score in enumerate((0.9, 0.8), start=1)
        ]

        answer = ExtractiveGenerator().generate("年假有多少天？", hits)

        self.assertEqual(answer.count(sentence), 1)
        self.assertTrue(answer.endswith("[1]"))


if __name__ == "__main__":
    unittest.main()
