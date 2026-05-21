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
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from academic_paper_cli.bibliography_manager import (
    BibliographyManagerError,
    list_bibliography,
    set_bibliography_record,
    show_bibliography_record,
)
from academic_paper_cli.models import (
    BibliographicAuthor,
    BibliographyCandidate,
    BibliographyIdentifierDiagnostic,
    BibliographicRecord,
    BulkBibliographyEnrichmentResult,
    BibliographyEnrichmentResult,
)
from academic_paper_cli.dataset_manager import list_documents


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


def diagnose_missing_identifiers(
    project_name: str,
    projects_root: Path = Path("projects"),
) -> list[BibliographyIdentifierDiagnostic]:
    """Report records that are not ready for identifier-based enrichment."""

    records = {record.document_id: record for record in list_bibliography(project_name, projects_root)}
    documents = {document.document_id: document for document in list_documents(project_name, projects_root)}
    diagnostics: list[BibliographyIdentifierDiagnostic] = []
    for document_id, record in sorted(records.items()):
        document = documents.get(document_id)
        has_identifier = bool(record.doi or record.isbn)
        if has_identifier or record.metadata_status == "verified":
            continue
        title = record.title
        suggestion = "Run biblio-search with the detected title or add DOI/ISBN manually."
        if not title:
            suggestion = "Add title/author manually or inspect the PDF; no identifier was detected."
        diagnostics.append(
            BibliographyIdentifierDiagnostic(
                document_id=document_id,
                original_filename=document.original_filename if document else "",
                title=title,
                year=record.year,
                doi=record.doi,
                isbn=record.isbn,
                status=record.metadata_status,
                suggestion=suggestion,
            )
        )
    return diagnostics


def search_bibliography_candidates(
    project_name: str,
    document_id: str,
    projects_root: Path = Path("projects"),
    title: str | None = None,
    author: str | None = None,
    limit: int = 5,
    fetcher: Fetcher | None = None,
) -> list[BibliographyCandidate]:
    """Search external services for candidate bibliographic records."""

    fetch = fetcher or _fetch_json
    record = show_bibliography_record(project_name, document_id, projects_root)
    query_title = (title or record.title).strip()
    if not query_title:
        raise BibliographyEnrichmentError(
            "Provide --title or set a title in the bibliographic record first."
        )
    query_author = (author or _first_author_name(record)).strip()
    candidates = _search_candidate_sources(query_title, query_author, limit, fetch)
    if not candidates and query_author:
        candidates = _search_candidate_sources(query_title, "", limit, fetch)
    candidates = _rank_candidates(candidates, query_title, query_author)[:limit]
    _store_candidates(project_name, document_id, projects_root, candidates)
    return candidates


def accept_bibliography_candidate(
    project_name: str,
    document_id: str,
    candidate_number: int,
    projects_root: Path = Path("projects"),
    verified: bool = False,
    force: bool = False,
) -> BibliographyEnrichmentResult:
    """Apply one previously stored candidate to a bibliographic record."""

    current = show_bibliography_record(project_name, document_id, projects_root)
    if current.metadata_status == "verified" and not force:
        raise BibliographyEnrichmentError(
            f"{document_id} is already verified. Use --force to overwrite curated metadata."
        )
    if candidate_number < 1:
        raise BibliographyEnrichmentError("--candidate must be 1 or greater.")
    if candidate_number > len(current.metadata_candidates):
        raise BibliographyEnrichmentError(
            f"{document_id} has only {len(current.metadata_candidates)} stored candidates. "
            "Run biblio-search first."
        )

    candidate = BibliographyCandidate.from_dict(
        current.metadata_candidates[candidate_number - 1]
    )
    updates = {
        "item_type": candidate.item_type,
        "title": candidate.title,
        "authors": candidate.authors,
        "year": candidate.year,
        "publisher": candidate.publisher,
        "journal": candidate.journal,
        "doi": candidate.doi,
        "isbn": candidate.isbn,
        "url": candidate.url,
        "citation_key": _citation_key(
            candidate.authors,
            candidate.year,
            candidate.title,
            document_id,
        ),
        "metadata_status": "verified" if verified else "needs_review",
        "verified": verified,
        "metadata_source": candidate.source,
        "metadata_source_url": candidate.url,
        "metadata_confidence": candidate.confidence,
        "metadata_enriched_at": _utc_now_iso(),
    }
    clean_updates = {
        key: value
        for key, value in updates.items()
        if value not in (None, "", [])
    }
    record = set_bibliography_record(
        project_name,
        document_id,
        projects_root,
        **clean_updates,
    )
    return BibliographyEnrichmentResult(
        record=record,
        enriched=True,
        source=candidate.source,
        source_url=candidate.url,
        message=f"Applied candidate #{candidate_number}.",
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


def _search_crossref_candidates(
    title: str,
    author: str,
    limit: int,
    fetcher: Fetcher,
) -> list[BibliographyCandidate]:
    params = {"query.title": title, "rows": str(limit)}
    if author:
        params["query.author"] = author
    url = f"https://api.crossref.org/works?{urlencode(params)}"
    payload = fetcher(url)
    items = payload.get("message", {}).get("items", [])
    candidates = []
    for item in items[:limit]:
        updates = _updates_from_crossref(item, str(item.get("DOI", "")), url)
        candidates.append(_candidate_from_updates("crossref", updates))
    return candidates


def _search_candidate_sources(
    title: str,
    author: str,
    limit: int,
    fetcher: Fetcher,
) -> list[BibliographyCandidate]:
    return [
        *_search_crossref_candidates(title, author, limit, fetcher),
        *_search_openlibrary_candidates(title, author, limit, fetcher),
    ]


def _search_openlibrary_candidates(
    title: str,
    author: str,
    limit: int,
    fetcher: Fetcher,
) -> list[BibliographyCandidate]:
    params = {"title": title, "limit": str(limit)}
    if author:
        params["author"] = author
    url = f"https://openlibrary.org/search.json?{urlencode(params)}"
    payload = fetcher(url)
    docs = payload.get("docs", [])
    candidates = []
    for doc in docs[:limit]:
        authors = [
            BibliographicAuthor.from_string(name)
            for name in doc.get("author_name", [])[:4]
        ]
        candidates.append(
            BibliographyCandidate(
                source="open_library",
                title=str(doc.get("title", "")).strip(),
                authors=authors,
                year=str(doc.get("first_publish_year", "")).strip(),
                item_type="book",
                isbn=_first(doc.get("isbn")),
                publisher=_first(doc.get("publisher")),
                url=f"https://openlibrary.org{doc.get('key', '')}" if doc.get("key") else "",
                confidence="medium",
            )
        )
    return candidates


def _candidate_from_updates(source: str, updates: dict[str, Any]) -> BibliographyCandidate:
    return BibliographyCandidate(
        source=source,
        title=str(updates.get("title", "")).strip(),
        authors=updates.get("authors", []),
        year=str(updates.get("year", "")).strip(),
        item_type=str(updates.get("item_type", "generic")).strip() or "generic",
        doi=str(updates.get("doi", "")).strip(),
        isbn=str(updates.get("isbn", "")).strip(),
        publisher=str(updates.get("publisher", "")).strip(),
        journal=str(updates.get("journal", "")).strip(),
        url=str(updates.get("url", "")).strip(),
        confidence="medium",
    )


def _store_candidates(
    project_name: str,
    document_id: str,
    projects_root: Path,
    candidates: list[BibliographyCandidate],
) -> None:
    existing = show_bibliography_record(project_name, document_id, projects_root)
    set_bibliography_record(
        project_name,
        document_id,
        projects_root,
        metadata_candidates=[candidate.to_dict() for candidate in candidates],
        metadata_status=existing.metadata_status,
    )


def _rank_candidates(
    candidates: list[BibliographyCandidate],
    title: str,
    author: str,
) -> list[BibliographyCandidate]:
    return sorted(
        candidates,
        key=lambda candidate: _candidate_score(candidate, title, author),
        reverse=True,
    )


def _candidate_score(candidate: BibliographyCandidate, title: str, author: str) -> float:
    query_title = _normalize_text(title)
    candidate_title = _normalize_text(candidate.title)
    score = 0.0
    if query_title and candidate_title == query_title:
        score += 2.0
    query_tokens = set(query_title.split())
    candidate_tokens = set(candidate_title.split())
    if query_tokens:
        score += len(query_tokens & candidate_tokens) / len(query_tokens)
    query_author = _normalize_text(author)
    candidate_authors = _normalize_text(
        " ".join(
            " ".join(part for part in [candidate_author.given, candidate_author.family] if part)
            for candidate_author in candidate.authors
        )
    )
    if query_author and query_author in candidate_authors:
        score += 1.0
    if candidate.isbn:
        score += 0.5
    if candidate.doi:
        score += 0.3
    if candidate.source == "open_library":
        score += 0.2
    return score


def _normalize_text(value: str) -> str:
    return " ".join(
        "".join(character.lower() if character.isalnum() else " " for character in value).split()
    )


def _first_author_name(record: BibliographicRecord) -> str:
    if not record.authors:
        return ""
    author = record.authors[0]
    return " ".join(part for part in [author.given, author.family] if part)


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
