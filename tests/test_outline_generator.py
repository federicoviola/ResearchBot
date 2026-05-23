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
from academic_paper_cli.outline_generator import generate_outline
from academic_paper_cli.project_manager import create_project


class OutlineGeneratorTests(unittest.TestCase):
    def test_generate_outline_uses_skill_and_saves_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            projects_root = _project_with_index(Path(temporary_directory))
            fake_client = FakeLLMClient(
                "# Outline\n\n## 1. Autonomy\nPurpose: frame autonomy.\nSources: doc_0001_chunk_0001\n"
            )

            result = generate_outline(
                "paper",
                "outline_design",
                projects_root,
                topic="autonomy and self institution",
                top_k=1,
                llm_client=fake_client,
            )

            self.assertIn("# Outline", result.outline)
            self.assertTrue(Path(result.output_path).is_file())
            self.assertTrue(Path(result.prompt_path).is_file())
            prompt = json.loads(Path(result.prompt_path).read_text(encoding="utf-8"))
            self.assertIn("Selected Skill: outline_design", prompt["messages"][1]["content"])
            self.assertIn("doc_0001_chunk_0001", prompt["messages"][1]["content"])

    def test_generate_outline_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            projects_root = _project_with_index(Path(temporary_directory))

            result = generate_outline(
                "paper",
                "outline_design",
                projects_root,
                topic="autonomy",
                top_k=1,
                dry_run=True,
            )

            self.assertTrue(result.dry_run)
            self.assertIn("DRY RUN", result.outline)
            self.assertTrue(Path(result.output_path).is_file())

    def test_generate_outline_limits_context_text_per_chunk(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            projects_root = _project_with_index(Path(temporary_directory))

            result = generate_outline(
                "paper",
                "outline_design",
                projects_root,
                topic="autonomy",
                top_k=1,
                context_chars=25,
                dry_run=True,
            )

            prompt = json.loads(Path(result.prompt_path).read_text(encoding="utf-8"))
            user_message = prompt["messages"][1]["content"]
            self.assertIn("Context truncated to 25 characters", user_message)
            self.assertEqual(result.context_chars, 25)

    def test_cli_outline_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            projects_root = _project_with_index(Path(temporary_directory))

            exit_code = main(
                [
                    "outline",
                    "--project",
                    "paper",
                    "--skill",
                    "outline_design",
                    "--topic",
                    "autonomy",
                    "--top-k",
                    "1",
                    "--context-chars",
                    "25",
                    "--dry-run",
                    "--projects-root",
                    str(projects_root),
                ]
            )

            self.assertEqual(exit_code, 0)


class FakeLLMClient:
    def __init__(self, answer: str) -> None:
        self.answer = answer

    def complete(self, messages: list[dict[str, str]]) -> str:
        return self.answer


def _project_with_index(root: Path) -> Path:
    projects_root = root / "projects"
    source_pdf = root / "source.pdf"
    source_pdf.write_bytes(b"%PDF-1.4\noutline fixture\n%%EOF\n")
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
