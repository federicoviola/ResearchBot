"""Bibliographic metadata enrichment from external identifier APIs.

This module enriches citation metadata only. It must not be used as paper
content evidence or as a source of academic claims.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from academic_paper_cli.bibliography_manager import (
    BibliographyManagerError,
    list_bibliography,
    set_bibliography_record,
    show_bibliography_record,
)
from academic_paper_cli.models import (
    BibliographicAuthor,
    BibliographicRecord,
    BulkBibliographyEnrichmentResult,
    BibliographyEnrichmentResult,
)


Fetcher = Callable[[str], dict[str, Any]]


class BibliographyEnrichmentError(ValueError):
    """Raised when external metadata enrichment cannot proceed."""


def enrich_bibliography_record(
    project_name: str,
    document_id: str,
    projects_root: Path = Path("projects"),
    doi: str | None = None,
    isbn: str | None = None,
    auto_verify: bool = False,
    force: bool = False,
    fetcher: Fetcher | None = None,
) -> BibliographyEnrichmentResult:
    """Enrich one bibliographic record from DOI or ISBN metadata."""

    if not doi and not isbn:
        current = show_bibliography_record(project_name, document_id, projects_root)
        doi = current.doi or None
        isbn = current.isbn or None

    if doi:
        return _enrich_from_doi(
            project_name,
            document_id,
            projects_root,
            doi,
            auto_verify,
            force,
            fetcher or _fetch_json,
        )
    if isbn:
        return _enrich_from_isbn(
            project_name,
            document_id,
            projects_root,
            isbn,
            auto_verify,
            force,
            fetcher or _fetch_json,
        )

    raise BibliographyEnrichmentError(
        "Provide --doi or --isbn, or store one of them in the bibliographic record first."
    )


def enrich_all_bibliography_records(
    project_name: str,
    projects_root: Path = Path("projects"),
    auto_verify: bool = False,
    force: bool = False,
    fetcher: Fetcher | None = None,
) -> BulkBibliographyEnrichmentResult:
    """Enrich all records that already contain DOI or ISBN metadata."""

    records = list_bibliography(project_name, projects_root)
    results: list[BibliographyEnrichmentResult] = []
    skipped: list[str] = []
    failed: dict[str, str] = {}

    for record in records:
        if not record.doi and not record.isbn:
            skipped.append(record.document_id)
            continue
        try:
            results.append(
                enrich_bibliography_record(
                    project_name=project_name,
                    document_id=record.document_id,
                    projects_root=projects_root,
                    doi=record.doi or None,
                    isbn=record.isbn or None,
                    auto_verify=auto_verify,
                    force=force,
                    fetcher=fetcher,
                )
            )
        except Exception as error:
            failed[record.document_id] = str(error)

    return BulkBibliographyEnrichmentResult(
        results=results,
        skipped=skipped,
        failed=failed,
    )


def _enrich_from_doi(
    project_name: str,
    document_id: str,
    projects_root: Path,
    doi: str,
    auto_verify: bool,
    force: bool,
    fetcher: Fetcher,
) -> BibliographyEnrichmentResult:
    normalized_doi = _normalize_doi(doi)
    crossref_url = f"https://api.crossref.org/works/{quote(normalized_doi, safe='')}"
    try:
        payload = fetcher(crossref_url)
        message = payload.get("message", {})
        updates = _updates_from_crossref(message, normalized_doi, crossref_url)
        record = _apply_enrichment(
            project_name,
            document_id,
            projects_root,
            updates,
            auto_verify,
            force,
        )
        return BibliographyEnrichmentResult(
            record=record,
            enriched=True,
            source="crossref",
            source_url=crossref_url,
            message="Metadata enriched from Crossref DOI lookup.",
        )
    except (BibliographyEnrichmentError, BibliographyManagerError):
        raise
    except Exception:
        datacite_url = f"https://api.datacite.org/dois/{quote(normalized_doi, safe='')}"
        payload = fetcher(datacite_url)
        data = payload.get("data", {})
        updates = _updates_from_datacite(data, normalized_doi, datacite_url)
        record = _apply_enrichment(
            project_name,
            document_id,
            projects_root,
            updates,
            auto_verify,
            force,
        )
        return BibliographyEnrichmentResult(
            record=record,
            enriched=True,
            source="datacite",
            source_url=datacite_url,
            message="Metadata enriched from DataCite DOI lookup.",
        )


def _enrich_from_isbn(
    project_name: str,
    document_id: str,
    projects_root: Path,
    isbn: str,
    auto_verify: bool,
    force: bool,
    fetcher: Fetcher,
) -> BibliographyEnrichmentResult:
    normalized_isbn = re.sub(r"[^0-9Xx]", "", isbn)
    if not normalized_isbn:
        raise BibliographyEnrichmentError("ISBN cannot be empty.")
    source_url = f"https://openlibrary.org/isbn/{normalized_isbn}.json"
    payload = fetcher(source_url)
    updates = _updates_from_openlibrary(payload, normalized_isbn, source_url, fetcher)
    record = _apply_enrichment(
        project_name,
        document_id,
        projects_root,
        updates,
        auto_verify,
        force,
    )
    return BibliographyEnrichmentResult(
        record=record,
        enriched=True,
        source="open_library",
        source_url=source_url,
        message="Metadata enriched from Open Library ISBN lookup.",
    )


def _apply_enrichment(
    project_name: str,
    document_id: str,
    projects_root: Path,
    updates: dict[str, Any],
    auto_verify: bool,
    force: bool,
) -> BibliographicRecord:
    current = show_bibliography_record(project_name, document_id, projects_root)
    if current.metadata_status == "verified" and not force:
        raise BibliographyEnrichmentError(
            f"{document_id} is already verified. Use --force to overwrite curated metadata."
        )

    clean_updates = {
        key: value
        for key, value in updates.items()
        if value not in (None, "", [])
    }
    if current.citation_key in ("", document_id):
        clean_updates["citation_key"] = _citation_key(
            clean_updates.get("authors", current.authors),
            str(clean_updates.get("year", current.year)),
            str(clean_updates.get("title", current.title)),
            document_id,
        )
    clean_updates["metadata_status"] = "verified" if auto_verify else "needs_review"
    clean_updates["verified"] = auto_verify
    clean_updates["metadata_enriched_at"] = _utc_now_iso()
    return set_bibliography_record(
        project_name,
        document_id,
        projects_root,
        **clean_updates,
    )


def _updates_from_crossref(
    message: dict[str, Any],
    doi: str,
    source_url: str,
) -> dict[str, Any]:
    title = _first(message.get("title"))
    authors = [
        BibliographicAuthor(
            family=str(author.get("family", "")).strip(),
            given=str(author.get("given", "")).strip(),
        )
        for author in message.get("author", [])
        if isinstance(author, dict) and author.get("family")
    ]
    issued = message.get("issued", {}).get("date-parts", [[]])
    year = str(issued[0][0]) if issued and issued[0] else ""
    item_type = _crossref_type(str(message.get("type", "")))
    return {
        "item_type": item_type,
        "title": title,
        "authors": authors,
        "year": year,
        "publisher": str(message.get("publisher", "")).strip(),
        "journal": _first(message.get("container-title")),
        "volume": str(message.get("volume", "")).strip(),
        "issue": str(message.get("issue", "")).strip(),
        "pages": str(message.get("page", "")).strip(),
        "doi": doi,
        "isbn": _first(message.get("ISBN")),
        "url": str(message.get("URL", "")).strip(),
        "citation_key": "",
        "metadata_source": "crossref",
        "metadata_source_url": source_url,
        "metadata_confidence": "high",
    }


def _updates_from_datacite(
    data: dict[str, Any],
    doi: str,
    source_url: str,
) -> dict[str, Any]:
    attributes = data.get("attributes", {})
    creators = attributes.get("creators", [])
    authors = []
    for creator in creators:
        if not isinstance(creator, dict):
            continue
        name = str(creator.get("name", "")).strip()
        family, given = _split_name(name)
        authors.append(BibliographicAuthor(family=family, given=given))

    return {
        "item_type": "generic",
        "title": _first(attributes.get("titles"), key="title"),
        "authors": authors,
        "year": str(attributes.get("publicationYear", "")).strip(),
        "publisher": str(attributes.get("publisher", "")).strip(),
        "doi": doi,
        "url": str(attributes.get("url", "")).strip(),
        "citation_key": "",
        "metadata_source": "datacite",
        "metadata_source_url": source_url,
        "metadata_confidence": "high",
    }


def _updates_from_openlibrary(
    payload: dict[str, Any],
    isbn: str,
    source_url: str,
    fetcher: Fetcher,
) -> dict[str, Any]:
    authors = _openlibrary_authors(payload, fetcher)
    return {
        "item_type": "book",
        "title": str(payload.get("title", "")).strip(),
        "authors": authors,
        "year": _year_from_publish_date(str(payload.get("publish_date", ""))),
        "publisher": _first(payload.get("publishers")),
        "place": _first(payload.get("publish_places")),
        "isbn": isbn,
        "citation_key": "",
        "metadata_source": "open_library",
        "metadata_source_url": source_url,
        "metadata_confidence": "high" if payload.get("title") else "medium",
    }


def _openlibrary_authors(payload: dict[str, Any], fetcher: Fetcher) -> list[BibliographicAuthor]:
    authors: list[BibliographicAuthor] = []
    for author_ref in payload.get("authors", []):
        key = author_ref.get("key") if isinstance(author_ref, dict) else None
        if not key:
            continue
        try:
            author_payload = fetcher(f"https://openlibrary.org{key}.json")
        except Exception:
            continue
        name = str(author_payload.get("name", "")).strip()
        if name:
            family, given = _split_name(name)
            authors.append(BibliographicAuthor(family=family, given=given))
    return authors


def _fetch_json(url: str) -> dict[str, Any]:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "ResearchBot/0.1 (metadata enrichment; mailto:researchbot@example.com)",
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise BibliographyEnrichmentError(f"Metadata lookup failed: HTTP {error.code}") from error
    except URLError as error:
        raise BibliographyEnrichmentError(f"Metadata lookup failed: {error.reason}") from error
    except json.JSONDecodeError as error:
        raise BibliographyEnrichmentError(f"Metadata lookup returned invalid JSON: {url}") from error


def _normalize_doi(doi: str) -> str:
    value = doi.strip()
    value = re.sub(r"^https?://(dx\.)?doi\.org/", "", value, flags=re.IGNORECASE)
    if not value:
        raise BibliographyEnrichmentError("DOI cannot be empty.")
    return value


def _first(value: Any, key: str | None = None) -> str:
    if isinstance(value, list) and value:
        first = value[0]
        if key and isinstance(first, dict):
            return str(first.get(key, "")).strip()
        return str(first).strip()
    return str(value or "").strip()


def _split_name(name: str) -> tuple[str, str]:
    if "," in name:
        family, given = name.split(",", 1)
        return family.strip(), given.strip()
    parts = name.split()
    if len(parts) > 1:
        return parts[-1], " ".join(parts[:-1])
    return name, ""


def _year_from_publish_date(value: str) -> str:
    match = re.search(r"(15|16|17|18|19|20)\d{2}", value)
    return match.group(0) if match else ""


def _crossref_type(value: str) -> str:
    return {
        "journal-article": "journal_article",
        "book": "book",
        "book-chapter": "book_chapter",
        "proceedings-article": "conference_paper",
        "posted-content": "generic",
        "dissertation": "thesis",
    }.get(value, "generic")


def _citation_key(
    authors: Any,
    year: str,
    title: str,
    fallback: str,
) -> str:
    family = ""
    if authors:
        first = authors[0]
        if isinstance(first, BibliographicAuthor):
            family = first.family
        elif isinstance(first, dict):
            family = str(first.get("family", ""))
    title_part = title.split()[0] if title else ""
    parts = [family, year, title_part]
    key = "_".join(_slug(part) for part in parts if part)
    return key or fallback


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", value.strip().lower()).strip("_")


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()
