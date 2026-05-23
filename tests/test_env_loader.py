from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from academic_paper_cli.env_loader import load_env_file


class EnvLoaderTests(unittest.TestCase):
    def test_load_env_file_sets_simple_values_without_overriding_existing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "# local secrets",
                        "OPENAI_API_KEY=from-file",
                        'LM_STUDIO_API_KEY="lm-studio"',
                        "export OLLAMA_API_KEY=ollama",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"OPENAI_API_KEY": "already-set"}, clear=True):
                loaded = load_env_file(env_path)

                self.assertEqual(os.environ["OPENAI_API_KEY"], "already-set")
                self.assertEqual(os.environ["LM_STUDIO_API_KEY"], "lm-studio")
                self.assertEqual(os.environ["OLLAMA_API_KEY"], "ollama")
                self.assertNotIn("OPENAI_API_KEY", loaded)

    def test_load_env_file_rejects_invalid_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text("OPENAI_API_KEY\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                load_env_file(env_path)


if __name__ == "__main__":
    unittest.main()
