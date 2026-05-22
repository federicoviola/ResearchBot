from __future__ import annotations

import unittest
import json
from unittest.mock import MagicMock, patch

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

    def test_openai_compatible_client_reports_reasoning_only_length_response(self) -> None:
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
        response = {
            "choices": [
                {
                    "message": {
                        "content": "",
                        "reasoning_content": "Thinking without final answer.",
                    },
                    "finish_reason": "length",
                }
            ]
        }
        fake_http_response = MagicMock()
        fake_http_response.__enter__.return_value.read.return_value = json.dumps(response).encode(
            "utf-8"
        )

        with patch("academic_paper_cli.llm_client.urlopen", return_value=fake_http_response):
            with self.assertRaises(LLMClientError) as context:
                client.complete([{"role": "user", "content": "hello"}])

        self.assertIn("used the available completion tokens for reasoning", str(context.exception))


if __name__ == "__main__":
    unittest.main()
