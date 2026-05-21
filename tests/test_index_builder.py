from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from academic_paper_cli.bibliography_manager import init_bibliography, set_bibliography_record
from academic_paper_cli.cli import main
from academic_paper_cli.dataset_manager import add_pdf
from academic_paper_cli.index_builder import IndexBuilderError, build_index, get_index_status
from academic_paper_cli.models import BibliographicAuthor
from academic_paper_cli.project_manager import create_project


class IndexBuilderTests(unittest.TestCase):
    def test_build_index_chunks_texts_and_writes_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            projects_root = _project_with_text(Path(temporary_directory))

            result = build_index(
                "paper",
                projects_root,
                chunk_size=5,
                chunk_overlap=1,
                embedding_dimensions=16,
            )

            self.assertEqual(result.document_count, 1)
            self.assertEqual(result.chunk_count, 3)
            self.assertEqual(result.embedding_backend, "hashing")
            chunks = _read_jsonl(Path(result.chunks_path))
            embeddings = _read_jsonl(Path(result.embeddings_path))
            self.assertEqual(chunks[0]["chunk_id"], "doc_0001_chunk_0001")
            self.assertEqual(chunks[0]["title"], "Autonomy and Institutions")
            self.assertEqual(chunks[0]["authors"], ["Viola, Federico"])
            self.assertEqual(len(embeddings[0]["embedding"]), 16)

    def test_build_index_requires_force_for_existing_index(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            projects_root = _project_with_text(Path(temporary_directory))
            build_index("paper", projects_root, chunk_size=5, chunk_overlap=1)

            with self.assertRaises(IndexBuilderError):
                build_index("paper", projects_root, chunk_size=5, chunk_overlap=1)

            rebuilt = build_index("paper", projects_root, force=True, chunk_size=4, chunk_overlap=0)

            self.assertGreater(rebuilt.chunk_count, 0)

    def test_index_status_reports_not_built_and_built(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            projects_root = _project_with_text(Path(temporary_directory))

            initial = get_index_status("paper", projects_root)

            self.assertEqual(initial.status, "not_built")

            build_index("paper", projects_root, chunk_size=5, chunk_overlap=1)
            built = get_index_status("paper", projects_root)

            self.assertEqual(built.status, "built")
            self.assertEqual(built.document_count, 1)
            self.assertEqual(built.chunk_count, 3)

    def test_cli_build_index_and_index_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            projects_root = _project_with_text(Path(temporary_directory))

            build_exit = main(
                [
                    "build-index",
                    "--project",
                    "paper",
                    "--projects-root",
                    str(projects_root),
                    "--chunk-size",
                    "5",
                    "--chunk-overlap",
                    "1",
                ]
            )
            status_exit = main(
                [
                    "index-status",
                    "--project",
                    "paper",
                    "--projects-root",
                    str(projects_root),
                ]
            )

            self.assertEqual(build_exit, 0)
            self.assertEqual(status_exit, 0)


def _project_with_text(root: Path) -> Path:
    projects_root = root / "projects"
    source_pdf = root / "source.pdf"
    source_pdf.write_bytes(b"%PDF-1.4\nindex fixture\n%%EOF\n")
    create_project("paper", projects_root)
    add_pdf("paper", source_pdf, projects_root)
    init_bibliography("paper", projects_root)
    set_bibliography_record(
        "paper",
        "doc_0001",
        projects_root,
        title="Autonomy and Institutions",
        authors=[BibliographicAuthor.from_string("Viola, Federico")],
        year="2021",
    )
    text = "one two three four five six seven eight nine ten eleven twelve"
    (projects_root / "paper" / "dataset" / "txt" / "doc_0001.txt").write_text(
        text,
        encoding="utf-8",
    )
    return projects_root


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


if __name__ == "__main__":
    unittest.main()
