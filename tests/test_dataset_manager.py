from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from academic_paper_cli.cli import main
from academic_paper_cli.dataset_manager import (
    DatasetManagerError,
    add_pdf,
    add_pdfs,
    list_documents,
)
from academic_paper_cli.project_manager import create_project


class DatasetManagerTests(unittest.TestCase):
    def test_add_pdf_copies_and_registers_document(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            projects_root = root / "projects"
            source_pdf = root / "Castoriadis Autonomy.pdf"
            source_pdf.write_bytes(b"%PDF-1.4\nmodule two fixture\n%%EOF\n")
            create_project("paper", projects_root)

            result = add_pdf("paper", source_pdf, projects_root)

            self.assertTrue(result.added)
            self.assertEqual(result.record.document_id, "doc_0001")
            self.assertEqual(result.record.original_filename, source_pdf.name)
            self.assertTrue(Path(result.record.stored_path).is_file())
            self.assertIn("doc_0001__", Path(result.record.stored_path).name)

            state_path = projects_root / "paper" / "state" / "ingestion_state.json"
            state = json.loads(state_path.read_text())
            self.assertIn("doc_0001", state["documents"])

    def test_add_pdf_detects_duplicates_by_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            projects_root = root / "projects"
            first_pdf = root / "first.pdf"
            second_pdf = root / "second.pdf"
            content = b"%PDF-1.4\nsame content\n%%EOF\n"
            first_pdf.write_bytes(content)
            second_pdf.write_bytes(content)
            create_project("paper", projects_root)

            first = add_pdf("paper", first_pdf, projects_root)
            second = add_pdf("paper", second_pdf, projects_root)

            self.assertTrue(first.added)
            self.assertFalse(second.added)
            self.assertEqual(second.duplicate_of, "doc_0001")
            self.assertEqual(len(list_documents("paper", projects_root)), 1)

    def test_add_pdf_rejects_non_pdf_extension(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            projects_root = root / "projects"
            source_file = root / "notes.txt"
            source_file.write_text("not a pdf")
            create_project("paper", projects_root)

            with self.assertRaises(DatasetManagerError):
                add_pdf("paper", source_file, projects_root)

    def test_add_pdfs_registers_folder_pdfs_and_skips_non_pdfs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            projects_root = root / "projects"
            source_dir = root / "sources"
            source_dir.mkdir()
            (source_dir / "first.pdf").write_bytes(b"%PDF-1.4\nfirst\n%%EOF\n")
            (source_dir / "second.PDF").write_bytes(b"%PDF-1.4\nsecond\n%%EOF\n")
            (source_dir / "notes.txt").write_text("skip me")
            create_project("paper", projects_root)

            result = add_pdfs("paper", [source_dir], projects_root)

            self.assertEqual(result.added_count, 2)
            self.assertEqual(result.duplicate_count, 0)
            self.assertEqual(result.skipped_paths, [])
            self.assertEqual(len(list_documents("paper", projects_root)), 2)

    def test_add_pdfs_can_search_folders_recursively(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            projects_root = root / "projects"
            source_dir = root / "sources"
            nested_dir = source_dir / "nested"
            nested_dir.mkdir(parents=True)
            (nested_dir / "nested.pdf").write_bytes(b"%PDF-1.4\nnested\n%%EOF\n")
            create_project("paper", projects_root)

            with self.assertRaises(DatasetManagerError):
                add_pdfs("paper", [source_dir], projects_root)

            recursive = add_pdfs("paper", [source_dir], projects_root, recursive=True)

            self.assertEqual(recursive.added_count, 1)

    def test_add_pdfs_reports_duplicates_by_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            projects_root = root / "projects"
            source_dir = root / "sources"
            source_dir.mkdir()
            content = b"%PDF-1.4\nsame\n%%EOF\n"
            (source_dir / "first.pdf").write_bytes(content)
            (source_dir / "second.pdf").write_bytes(content)
            create_project("paper", projects_root)

            result = add_pdfs("paper", [source_dir], projects_root)

            self.assertEqual(result.added_count, 1)
            self.assertEqual(result.duplicate_count, 1)
            self.assertEqual(len(list_documents("paper", projects_root)), 1)

    def test_cli_add_pdf_and_list_docs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            projects_root = root / "projects"
            source_pdf = root / "source.pdf"
            source_pdf.write_bytes(b"%PDF-1.4\ncli fixture\n%%EOF\n")
            create_project("paper", projects_root)

            add_exit = main(
                [
                    "add-pdf",
                    "--project",
                    "paper",
                    "--file",
                    str(source_pdf),
                    "--projects-root",
                    str(projects_root),
                ]
            )
            list_exit = main(
                [
                    "list-docs",
                    "--project",
                    "paper",
                    "--projects-root",
                    str(projects_root),
                ]
            )

            self.assertEqual(add_exit, 0)
            self.assertEqual(list_exit, 0)

    def test_cli_add_pdfs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            projects_root = root / "projects"
            source_dir = root / "sources"
            source_dir.mkdir()
            (source_dir / "first.pdf").write_bytes(b"%PDF-1.4\nfirst\n%%EOF\n")
            (source_dir / "second.pdf").write_bytes(b"%PDF-1.4\nsecond\n%%EOF\n")
            create_project("paper", projects_root)

            exit_code = main(
                [
                    "add-pdfs",
                    "--project",
                    "paper",
                    "--path",
                    str(source_dir),
                    "--projects-root",
                    str(projects_root),
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertEqual(len(list_documents("paper", projects_root)), 2)


if __name__ == "__main__":
    unittest.main()
