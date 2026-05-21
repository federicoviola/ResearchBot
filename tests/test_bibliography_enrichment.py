from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from academic_paper_cli.bibliography_enrichment import enrich_bibliography_record
from academic_paper_cli.bibliography_manager import init_bibliography
from academic_paper_cli.cli import main
from academic_paper_cli.dataset_manager import add_pdf
from academic_paper_cli.project_manager import create_project


class BibliographyEnrichmentTests(unittest.TestCase):
    def test_enrich_from_crossref_doi(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            projects_root = _project_with_bibliography(Path(temporary_directory))

            result = enrich_bibliography_record(
                "paper",
                "doc_0001",
                projects_root,
                doi="10.1234/example",
                fetcher=_crossref_fetcher,
            )

            self.assertTrue(result.enriched)
            self.assertEqual(result.source, "crossref")
            self.assertEqual(result.record.item_type, "journal_article")
            self.assertEqual(result.record.title, "Autonomy and Institutions")
            self.assertEqual(result.record.year, "2021")
            self.assertEqual(result.record.journal, "Journal of Social Theory")
            self.assertEqual(result.record.metadata_status, "needs_review")
            self.assertEqual(result.record.metadata_source, "crossref")
            self.assertEqual(result.record.citation_key, "viola_2021_autonomy")

    def test_enrich_from_datacite_when_crossref_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            projects_root = _project_with_bibliography(Path(temporary_directory))

            result = enrich_bibliography_record(
                "paper",
                "doc_0001",
                projects_root,
                doi="10.9999/datacite",
                fetcher=_datacite_fallback_fetcher,
            )

            self.assertTrue(result.enriched)
            self.assertEqual(result.source, "datacite")
            self.assertEqual(result.record.title, "Dataset Metadata Example")
            self.assertEqual(result.record.year, "2020")
            self.assertEqual(result.record.publisher, "Zenodo")

    def test_enrich_from_openlibrary_isbn(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            projects_root = _project_with_bibliography(Path(temporary_directory))

            result = enrich_bibliography_record(
                "paper",
                "doc_0001",
                projects_root,
                isbn="9780262531559",
                auto_verify=True,
                fetcher=_openlibrary_fetcher,
            )

            self.assertTrue(result.enriched)
            self.assertEqual(result.source, "open_library")
            self.assertEqual(result.record.item_type, "book")
            self.assertEqual(result.record.title, "The Imaginary Institution of Society")
            self.assertEqual(result.record.authors[0].family, "Castoriadis")
            self.assertEqual(result.record.metadata_status, "verified")

    def test_cli_biblio_enrich_requires_identifier(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            projects_root = _project_with_bibliography(root)

            exit_code = main(
                [
                    "biblio-enrich",
                    "--project",
                    "paper",
                    "--doc-id",
                    "doc_0001",
                    "--projects-root",
                    str(projects_root),
                ]
            )

            self.assertEqual(exit_code, 1)


def _project_with_bibliography(root: Path) -> Path:
    projects_root = root / "projects"
    source_pdf = root / "source.pdf"
    source_pdf.write_bytes(b"%PDF-1.4\nmetadata enrichment fixture\n%%EOF\n")
    create_project("paper", projects_root)
    add_pdf("paper", source_pdf, projects_root)
    init_bibliography("paper", projects_root)
    return projects_root


def _crossref_fetcher(url: str):
    self_url = url
    return {
        "message": {
            "type": "journal-article",
            "title": ["Autonomy and Institutions"],
            "author": [{"family": "Viola", "given": "Federico"}],
            "issued": {"date-parts": [[2021, 5, 1]]},
            "container-title": ["Journal of Social Theory"],
            "volume": "12",
            "issue": "2",
            "page": "10-30",
            "publisher": "Example Press",
            "DOI": "10.1234/example",
            "URL": self_url,
        }
    }


def _datacite_fallback_fetcher(url: str):
    if "crossref" in url:
        raise RuntimeError("not found")
    return {
        "data": {
            "attributes": {
                "titles": [{"title": "Dataset Metadata Example"}],
                "creators": [{"name": "Doe, Jane"}],
                "publicationYear": 2020,
                "publisher": "Zenodo",
                "url": "https://example.org/dataset",
            }
        }
    }


def _openlibrary_fetcher(url: str):
    if "/authors/" in url:
        return {"name": "Cornelius Castoriadis"}
    return {
        "title": "The Imaginary Institution of Society",
        "authors": [{"key": "/authors/OL123A"}],
        "publish_date": "1987",
        "publishers": ["MIT Press"],
        "publish_places": ["Cambridge, MA"],
    }


if __name__ == "__main__":
    unittest.main()
