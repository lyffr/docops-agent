import unittest

from docops_agent.config import Settings


class SettingsTests(unittest.TestCase):
    def test_provider_is_normalized(self) -> None:
        settings = Settings(llm_provider=" OpenAI-Compatible ")

        self.assertEqual(settings.llm_provider, "openai-compatible")

    def test_invalid_values_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "DOCOPS_LLM_PROVIDER"):
            Settings(llm_provider="typo")
        with self.assertRaisesRegex(ValueError, "DOCOPS_TOP_K"):
            Settings(top_k=0)
        with self.assertRaisesRegex(ValueError, "DOCOPS_MIN_EVIDENCE_SCORE"):
            Settings(min_evidence_score=1.1)
        with self.assertRaisesRegex(ValueError, "DOCOPS_MAX_UPLOAD_BYTES"):
            Settings(max_upload_bytes=0)


if __name__ == "__main__":
    unittest.main()
