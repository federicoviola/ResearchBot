from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from academic_paper_cli.bibliography_manager import init_bibliography, set_bibliography_record
from academic_paper_cli.cli import main
from academic_paper_cli.dataset_manager import add_pdf
from academic_paper_cli.index_builder import build_index
from academic_paper_cli.models import BibliographicAuthor
from academic_paper_cli.project_manager import create_project
from academic_paper_cli.retrieval_engine import RetrievalEngineError, retrieve_chunks


class RetrievalEngineTests(unittest.TestCase):
    def test_retrieve_chunks_returns_ranked_local_results(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            projects_root = _project_with_index(Path(temporary_directory))

            results = retrieve_chunks(
                "paper",
                "autonomy self institution",
                projects_root,
                top_k=2,
            )

            self.assertEqual(len(results), 2)
            self.assertEqual(results[0].rank, 1)
            self.assertEqual(results[0].chunk.document_id, "doc_0001")
            self.assertIn("autonomy", results[0].chunk.text)
            self.assertGreaterEqual(results[0].score, results[1].score)

    def test_retrieve_chunks_requires_built_index(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            projects_root = _project_without_index(Path(temporary_directory))

            with self.assertRaises(RetrievalEngineError):
                retrieve_chunks("paper", "autonomy", projects_root)

    def test_cli_retrieve(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            projects_root = _project_with_index(Path(temporary_directory))

            exit_code = main(
                [
                    "retrieve",
                    "--project",
                    "paper",
                    "--top-k",
                    "2",
                    "--projects-root",
                    str(projects_root),
                    "autonomy self institution",
                ]
            )

            self.assertEqual(exit_code, 0)


def _project_without_index(root: Path) -> Path:
    projects_root = root / "projects"
    source_pdf = root / "source.pdf"
    source_pdf.write_bytes(b"%PDF-1.4\nretrieval fixture\n%%EOF\n")
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
        "biology metabolism cell membrane organism autopoiesis "
        "blockchain cryptography protocol consensus governance"
    )
    (projects_root / "paper" / "dataset" / "txt" / "doc_0001.txt").write_text(
        text,
        encoding="utf-8",
    )
    return projects_root


def _project_with_index(root: Path) -> Path:
    projects_root = _project_without_index(root)
    build_index("paper", projects_root, chunk_size=6, chunk_overlap=0)
    return projects_root


if __name__ == "__main__":
    unittest.main()
