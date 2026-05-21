from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from academic_paper_cli.bibliography_manager import init_bibliography, set_bibliography_record
from academic_paper_cli.cli import main
from academic_paper_cli.dataset_manager import add_pdf
from academic_paper_cli.index_builder import build_index
from academic_paper_cli.models import BibliographicAuthor
from academic_paper_cli.project_manager import create_project
from academic_paper_cli.query_engine import query_dataset


class QueryEngineTests(unittest.TestCase):
    def test_query_dataset_uses_retrieved_chunks_and_saves_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            projects_root = _project_with_index(Path(temporary_directory))
            fake_client = FakeLLMClient(
                "Autonomy is presented as self-institution in the retrieved corpus. "
                "Sources: doc_0001_chunk_0001."
            )

            result = query_dataset(
                "paper",
                "What does the dataset say about autonomy?",
                projects_root,
                top_k=1,
                llm_client=fake_client,
            )

            self.assertIn("self-institution", result.answer)
            self.assertEqual(len(result.retrieval_results), 1)
            self.assertTrue(Path(result.prompt_path).is_file())
            self.assertTrue(Path(result.response_path).is_file())
            prompt = json.loads(Path(result.prompt_path).read_text(encoding="utf-8"))
            self.assertIn("Retrieved Dataset Context", prompt["messages"][1]["content"])
            self.assertIn("doc_0001_chunk_0001", prompt["messages"][1]["content"])

    def test_query_dataset_dry_run_does_not_require_configured_model(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            projects_root = _project_with_index(Path(temporary_directory))

            result = query_dataset(
                "paper",
                "autonomy",
                projects_root,
                top_k=1,
                dry_run=True,
            )

            self.assertTrue(result.dry_run)
            self.assertIn("DRY RUN", result.answer)
            self.assertTrue(Path(result.prompt_path).is_file())

    def test_cli_query_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            projects_root = _project_with_index(Path(temporary_directory))

            exit_code = main(
                [
                    "query",
                    "--project",
                    "paper",
                    "--top-k",
                    "1",
                    "--dry-run",
                    "--projects-root",
                    str(projects_root),
                    "autonomy",
                ]
            )

            self.assertEqual(exit_code, 0)


class FakeLLMClient:
    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.messages = []

    def complete(self, messages: list[dict[str, str]]) -> str:
        self.messages = messages
        return self.answer


def _project_with_index(root: Path) -> Path:
    projects_root = root / "projects"
    source_pdf = root / "source.pdf"
    source_pdf.write_bytes(b"%PDF-1.4\nquery fixture\n%%EOF\n")
    create_project("paper", projects_root)
    add_pdf("paper", source_pdf, projects_root)
    init_bibliography("paper", projects_root)
    set_bibliography_record(
        "paper",
        "doc_0001",
        projects_root,
        title="Philosophy, Politics, Autonomy",
        authors=[BibliographicAuthor.from_string("Castoriadis, Cornelius")],
        year="1991",
    )
    text = (
        "autonomy self institution society democratic project "
        "heteronomy bureaucracy representation political creation"
    )
    (projects_root / "paper" / "dataset" / "txt" / "doc_0001.txt").write_text(
        text,
        encoding="utf-8",
    )
    build_index("paper", projects_root, chunk_size=6, chunk_overlap=0)
    return projects_root


if __name__ == "__main__":
    unittest.main()
