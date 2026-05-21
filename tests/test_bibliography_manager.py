from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import yaml

from academic_paper_cli.bibliography_manager import (
    export_bibliography,
    init_bibliography,
    set_bibliography_record,
    validate_bibliography,
)
from academic_paper_cli.cli import main
from academic_paper_cli.dataset_manager import add_pdf
from academic_paper_cli.pdf_processor import ingest_project
from academic_paper_cli.project_manager import create_project


class BibliographyManagerTests(unittest.TestCase):
    def test_init_bibliography_creates_editable_template(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            projects_root = root / "projects"
            source_pdf = root / "source.pdf"
            source_pdf.write_bytes(b"%PDF-1.4\nbibliography fixture\n%%EOF\n")
            create_project("paper", projects_root)
            add_pdf("paper", source_pdf, projects_root)

            records = init_bibliography("paper", projects_root)

            self.assertEqual(len(records), 1)
            record_path = (
                projects_root
                / "paper"
                / "dataset"
                / "bibliography"
                / "doc_0001.yaml"
            )
            self.assertTrue(record_path.is_file())
            payload = yaml.safe_load(record_path.read_text())
            self.assertEqual(payload["document_id"], "doc_0001")
            self.assertEqual(payload["metadata_status"], "needs_review")

    def test_init_bibliography_uses_ingested_identifiers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            projects_root = root / "projects"
            source_pdf = root / "source.pdf"
            _write_pdf(
                source_pdf,
                "DOI 10.1234/example.test ISBN 978-0-262-53155-9",
            )
            create_project("paper", projects_root)
            add_pdf("paper", source_pdf, projects_root)
            ingest_project("paper", projects_root)

            init_bibliography("paper", projects_root)

            record_path = (
                projects_root
                / "paper"
                / "dataset"
                / "bibliography"
                / "doc_0001.yaml"
            )
            payload = yaml.safe_load(record_path.read_text())
            self.assertEqual(payload["doi"], "10.1234/example.test")
            self.assertEqual(payload["isbn"], "9780262531559")

    def test_init_bibliography_refreshes_missing_identifiers_in_existing_records(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            projects_root = root / "projects"
            source_pdf = root / "source.pdf"
            _write_pdf(source_pdf, "DOI 10.1234/example.test")
            create_project("paper", projects_root)
            add_pdf("paper", source_pdf, projects_root)
            init_bibliography("paper", projects_root)
            ingest_project("paper", projects_root)

            init_bibliography("paper", projects_root)

            record_path = (
                projects_root
                / "paper"
                / "dataset"
                / "bibliography"
                / "doc_0001.yaml"
            )
            payload = yaml.safe_load(record_path.read_text())
            self.assertEqual(payload["doi"], "10.1234/example.test")

    def test_init_bibliography_cleans_existing_identifier_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            projects_root = root / "projects"
            source_pdf = root / "source.pdf"
            source_pdf.write_bytes(b"%PDF-1.4\nbibliography fixture\n%%EOF\n")
            create_project("paper", projects_root)
            add_pdf("paper", source_pdf, projects_root)
            init_bibliography("paper", projects_root)
            record_path = (
                projects_root
                / "paper"
                / "dataset"
                / "bibliography"
                / "doc_0001.yaml"
            )
            payload = yaml.safe_load(record_path.read_text())
            payload["doi"] = "10.4324/\u200b9781003039723"
            payload["isbn"] = "978-1-003-03972-3"
            record_path.write_text(yaml.safe_dump(payload, sort_keys=False))

            init_bibliography("paper", projects_root)

            cleaned = yaml.safe_load(record_path.read_text())
            self.assertEqual(cleaned["doi"], "10.4324/9781003039723")
            self.assertEqual(cleaned["isbn"], "9781003039723")

    def test_set_validate_and_export_bibliography(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            projects_root = root / "projects"
            source_pdf = root / "source.pdf"
            source_pdf.write_bytes(b"%PDF-1.4\nbibliography fixture\n%%EOF\n")
            create_project("paper", projects_root)
            add_pdf("paper", source_pdf, projects_root)
            init_bibliography("paper", projects_root)

            invalid = validate_bibliography("paper", projects_root)
            self.assertFalse(invalid[0].valid)

            set_bibliography_record(
                "paper",
                "doc_0001",
                projects_root,
                item_type="book",
                title="The Imaginary Institution of Society",
                authors=[],
                year="1987",
                publisher="MIT Press",
            )
            still_invalid = validate_bibliography("paper", projects_root)
            self.assertIn("authors", still_invalid[0].missing_fields)

            exit_code = main(
                [
                    "biblio-set",
                    "--project",
                    "paper",
                    "--doc-id",
                    "doc_0001",
                    "--type",
                    "book",
                    "--title",
                    "The Imaginary Institution of Society",
                    "--author",
                    "Castoriadis, Cornelius",
                    "--year",
                    "1987",
                    "--publisher",
                    "MIT Press",
                    "--citation-key",
                    "castoriadis_1987_imaginary",
                    "--verified",
                    "--projects-root",
                    str(projects_root),
                ]
            )
            self.assertEqual(exit_code, 0)

            valid = validate_bibliography("paper", projects_root)
            self.assertTrue(valid[0].valid)

            bibtex_path = export_bibliography("paper", projects_root, "bibtex")
            self.assertIn(
                "@book{castoriadis_1987_imaginary",
                bibtex_path.read_text(),
            )

            csl_path = export_bibliography("paper", projects_root, "csl-json")
            csl = json.loads(csl_path.read_text())
            self.assertEqual(csl[0]["id"], "castoriadis_1987_imaginary")

    def test_cli_bibliography_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            projects_root = root / "projects"
            source_pdf = root / "source.pdf"
            source_pdf.write_bytes(b"%PDF-1.4\nbibliography fixture\n%%EOF\n")
            create_project("paper", projects_root)
            add_pdf("paper", source_pdf, projects_root)

            init_exit = main(
                [
                    "biblio-init",
                    "--project",
                    "paper",
                    "--projects-root",
                    str(projects_root),
                ]
            )
            list_exit = main(
                [
                    "biblio-list",
                    "--project",
                    "paper",
                    "--projects-root",
                    str(projects_root),
                ]
            )
            validate_exit = main(
                [
                    "biblio-validate",
                    "--project",
                    "paper",
                    "--projects-root",
                    str(projects_root),
                ]
            )

            self.assertEqual(init_exit, 0)
            self.assertEqual(list_exit, 0)
            self.assertEqual(validate_exit, 2)


if __name__ == "__main__":
    unittest.main()


def _write_pdf(path: Path, text: str) -> None:
    import fitz

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    document.save(path)
    document.close()
