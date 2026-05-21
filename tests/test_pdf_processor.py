from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import fitz

from academic_paper_cli.cli import main
from academic_paper_cli.dataset_manager import add_pdf
from academic_paper_cli.pdf_processor import ingest_project
from academic_paper_cli.project_manager import create_project


class PdfProcessorTests(unittest.TestCase):
    def test_ingest_project_extracts_text_metadata_and_updates_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            projects_root = root / "projects"
            source_pdf = root / "autonomy.pdf"
            _write_pdf(source_pdf, "Autonomy appears in this fixture.")
            create_project("paper", projects_root)
            add_pdf("paper", source_pdf, projects_root)

            results = ingest_project("paper", projects_root)

            self.assertEqual(len(results), 1)
            result = results[0]
            self.assertEqual(result.status, "ingested")
            self.assertEqual(result.page_count, 1)
            self.assertGreater(result.word_count, 0)
            self.assertIsNotNone(result.text_path)
            self.assertIsNotNone(result.metadata_path)
            self.assertIn("Autonomy appears", Path(result.text_path).read_text())

            metadata = json.loads(Path(result.metadata_path).read_text())
            self.assertEqual(metadata["document_id"], "doc_0001")
            self.assertEqual(metadata["page_count"], 1)
            self.assertEqual(metadata["extraction"]["tool"], "PyMuPDF")

            state_path = projects_root / "paper" / "state" / "ingestion_state.json"
            state = json.loads(state_path.read_text())
            record = state["documents"]["doc_0001"]
            self.assertEqual(record["status"], "ingested")
            self.assertEqual(record["text_path"], result.text_path)
            self.assertEqual(record["metadata_path"], result.metadata_path)

    def test_ingest_detects_doi_and_isbn_identifiers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            projects_root = root / "projects"
            source_pdf = root / "identifiers.pdf"
            _write_pdf(
                source_pdf,
                "DOI: 10.1234/example.test ISBN 978-0-262-53155-9",
            )
            create_project("paper", projects_root)
            add_pdf("paper", source_pdf, projects_root)

            result = ingest_project("paper", projects_root)[0]

            metadata = json.loads(Path(result.metadata_path).read_text())
            self.assertEqual(metadata["identifiers"]["doi"], ["10.1234/example.test"])
            self.assertEqual(metadata["identifiers"]["isbn"], ["9780262531559"])

    def test_ingest_skips_already_ingested_documents_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            projects_root = root / "projects"
            source_pdf = root / "source.pdf"
            _write_pdf(source_pdf, "First text.")
            create_project("paper", projects_root)
            add_pdf("paper", source_pdf, projects_root)
            first = ingest_project("paper", projects_root)

            second = ingest_project("paper", projects_root)

            self.assertEqual(first[0].status, "ingested")
            self.assertEqual(second[0].status, "skipped")

    def test_cli_ingest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            projects_root = root / "projects"
            source_pdf = root / "source.pdf"
            _write_pdf(source_pdf, "CLI ingestion fixture.")
            create_project("paper", projects_root)
            add_pdf("paper", source_pdf, projects_root)

            exit_code = main(
                [
                    "ingest",
                    "--project",
                    "paper",
                    "--projects-root",
                    str(projects_root),
                ]
            )

            self.assertEqual(exit_code, 0)


def _write_pdf(path: Path, text: str) -> None:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    document.save(path)
    document.close()


if __name__ == "__main__":
    unittest.main()
