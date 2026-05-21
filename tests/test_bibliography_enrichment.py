from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from academic_paper_cli.bibliography_enrichment import accept_bibliography_candidate
from academic_paper_cli.bibliography_enrichment import diagnose_missing_identifiers
from academic_paper_cli.bibliography_enrichment import enrich_all_bibliography_records
from academic_paper_cli.bibliography_enrichment import enrich_bibliography_record
from academic_paper_cli.bibliography_enrichment import search_bibliography_candidates
from academic_paper_cli.bibliography_manager import init_bibliography
from academic_paper_cli.bibliography_manager import set_bibliography_record
from academic_paper_cli.cli import main
from academic_paper_cli.models import BibliographicAuthor
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

    def test_enrich_all_uses_stored_identifiers_and_skips_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            projects_root = root / "projects"
            create_project("paper", projects_root)
            first_pdf = root / "first.pdf"
            second_pdf = root / "second.pdf"
            third_pdf = root / "third.pdf"
            first_pdf.write_bytes(b"%PDF-1.4\nfirst\n%%EOF\n")
            second_pdf.write_bytes(b"%PDF-1.4\nsecond\n%%EOF\n")
            third_pdf.write_bytes(b"%PDF-1.4\nthird\n%%EOF\n")
            add_pdf("paper", first_pdf, projects_root)
            add_pdf("paper", second_pdf, projects_root)
            add_pdf("paper", third_pdf, projects_root)
            init_bibliography("paper", projects_root)
            set_bibliography_record(
                "paper",
                "doc_0001",
                projects_root,
                doi="10.1234/example",
            )
            set_bibliography_record(
                "paper",
                "doc_0002",
                projects_root,
                isbn="9780262531559",
            )

            result = enrich_all_bibliography_records(
                "paper",
                projects_root,
                fetcher=_mixed_fetcher,
            )

            self.assertEqual(result.enriched_count, 2)
            self.assertEqual(result.skipped, ["doc_0003"])
            self.assertEqual(result.failed_count, 0)

    def test_cli_biblio_enrich_all_requires_no_doc_id(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            projects_root = _project_with_bibliography(Path(temporary_directory))

            exit_code = main(
                [
                    "biblio-enrich",
                    "--project",
                    "paper",
                    "--all",
                    "--projects-root",
                    str(projects_root),
                ]
            )

            self.assertEqual(exit_code, 0)

    def test_diagnose_missing_identifiers_reports_records_without_doi_or_isbn(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            projects_root = _project_with_bibliography(Path(temporary_directory))

            diagnostics = diagnose_missing_identifiers("paper", projects_root)

            self.assertEqual(len(diagnostics), 1)
            self.assertEqual(diagnostics[0].document_id, "doc_0001")
            self.assertIn("Add title", diagnostics[0].suggestion)

    def test_diagnose_missing_identifiers_ignores_verified_records(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            projects_root = _project_with_bibliography(Path(temporary_directory))
            set_bibliography_record(
                "paper",
                "doc_0001",
                projects_root,
                title="Philosophy, Politics, Autonomy",
                authors=[BibliographicAuthor.from_string("Castoriadis, Cornelius")],
                year="1991",
                verified=True,
            )

            diagnostics = diagnose_missing_identifiers("paper", projects_root)

            self.assertEqual(diagnostics, [])

    def test_search_bibliography_candidates_stores_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            projects_root = _project_with_bibliography(Path(temporary_directory))
            set_bibliography_record(
                "paper",
                "doc_0001",
                projects_root,
                title="Autonomy and Institutions",
                authors=[],
            )

            candidates = search_bibliography_candidates(
                "paper",
                "doc_0001",
                projects_root,
                fetcher=_candidate_fetcher,
            )

            self.assertEqual(len(candidates), 2)
            self.assertEqual(candidates[0].source, "open_library")
            self.assertEqual(candidates[1].source, "crossref")

    def test_search_bibliography_candidates_retries_without_bad_author(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            projects_root = _project_with_bibliography(Path(temporary_directory))
            set_bibliography_record(
                "paper",
                "doc_0001",
                projects_root,
                title="Philosophy, Politics, Autonomy",
                authors=[BibliographicAuthor.from_string("XOLOTL")],
            )

            candidates = search_bibliography_candidates(
                "paper",
                "doc_0001",
                projects_root,
                fetcher=_author_sensitive_candidate_fetcher,
            )

            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0].source, "open_library")
            self.assertEqual(candidates[0].title, "Philosophy, politics, autonomy")

    def test_accept_bibliography_candidate_applies_stored_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            projects_root = _project_with_bibliography(Path(temporary_directory))
            set_bibliography_record(
                "paper",
                "doc_0001",
                projects_root,
                title="Autonomy and Institutions",
                authors=[],
                citation_key="stale_key",
            )
            search_bibliography_candidates(
                "paper",
                "doc_0001",
                projects_root,
                fetcher=_candidate_fetcher,
            )

            result = accept_bibliography_candidate(
                "paper",
                "doc_0001",
                1,
                projects_root,
                verified=True,
            )

            self.assertTrue(result.enriched)
            self.assertEqual(result.record.metadata_status, "verified")
            self.assertEqual(result.record.metadata_source, "open_library")
            self.assertEqual(result.record.title, "Autonomy and Institutions")
            self.assertEqual(result.record.year, "2021")
            self.assertEqual(result.record.publisher, "Example Press")
            self.assertEqual(result.record.citation_key, "federico_viola_2021_autonomy")

    def test_cli_biblio_accept_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            projects_root = _project_with_bibliography(Path(temporary_directory))
            set_bibliography_record(
                "paper",
                "doc_0001",
                projects_root,
                metadata_candidates=[
                    {
                        "source": "open_library",
                        "title": "Philosophy, politics, autonomy",
                        "authors": [{"family": "Castoriadis", "given": "Cornelius"}],
                        "year": "1991",
                        "item_type": "book",
                        "publisher": "Oxford University Press",
                        "confidence": "medium",
                    }
                ],
            )

            exit_code = main(
                [
                    "biblio-accept-candidate",
                    "--project",
                    "paper",
                    "--doc-id",
                    "doc_0001",
                    "--candidate",
                    "1",
                    "--verified",
                    "--projects-root",
                    str(projects_root),
                ]
            )

            self.assertEqual(exit_code, 0)

    def test_cli_biblio_missing_identifiers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            projects_root = _project_with_bibliography(Path(temporary_directory))

            exit_code = main(
                [
                    "biblio-missing-identifiers",
                    "--project",
                    "paper",
                    "--projects-root",
                    str(projects_root),
                ]
            )

            self.assertEqual(exit_code, 0)


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


def _mixed_fetcher(url: str):
    if "crossref" in url:
        return _crossref_fetcher(url)
    return _openlibrary_fetcher(url)


def _candidate_fetcher(url: str):
    if "crossref" in url:
        return {
            "message": {
                "items": [
                    {
                        "type": "journal-article",
                        "title": ["Autonomy and Institutions"],
                        "author": [{"family": "Viola", "given": "Federico"}],
                        "issued": {"date-parts": [[2021]]},
                        "container-title": ["Journal of Social Theory"],
                        "DOI": "10.1234/example",
                    }
                ]
            }
        }
    return {
        "docs": [
            {
                "title": "Autonomy and Institutions",
                "author_name": ["Federico Viola"],
                "first_publish_year": 2021,
                "isbn": ["9781234567890"],
                "publisher": ["Example Press"],
                "key": "/works/OL1W",
            }
        ]
    }


def _author_sensitive_candidate_fetcher(url: str):
    if "author=XOLOTL" in url:
        if "crossref" in url:
            return {"message": {"items": []}}
        return {"docs": []}
    if "crossref" in url:
        return {"message": {"items": []}}
    return {
        "docs": [
            {
                "title": "Philosophy, politics, autonomy",
                "author_name": ["Cornelius Castoriadis"],
                "first_publish_year": 1991,
                "key": "/works/OL1W",
            }
        ]
    }


if __name__ == "__main__":
    unittest.main()
