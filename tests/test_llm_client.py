from __future__ import annotations

import unittest
from unittest.mock import patch

from academic_paper_cli.llm_client import LLMClientError, LLMSettings, OpenAICompatibleClient


class LLMClientTests(unittest.TestCase):
    def test_openai_compatible_client_reports_timeout_cleanly(self) -> None:
        settings = LLMSettings(
            provider="openai_compatible",
            base_url="http://localhost:1234/v1",
            model="local-model",
            api_key_env="TEST_API_KEY",
            temperature=0.2,
            max_tokens=100,
            timeout_seconds=1,
        )
        client = OpenAICompatibleClient(settings)

        with patch("academic_paper_cli.llm_client.urlopen", side_effect=TimeoutError):
            with self.assertRaises(LLMClientError) as context:
                client.complete([{"role": "user", "content": "hello"}])

        self.assertIn("timed out after 1 seconds", str(context.exception))


if __name__ == "__main__":
    unittest.main()
