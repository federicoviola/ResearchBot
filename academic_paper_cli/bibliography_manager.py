"""Bibliographic metadata manager for academic citation readiness."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from academic_paper_cli.dataset_manager import list_documents
from academic_paper_cli.models import (
    BibliographicAuthor,
    BibliographicRecord,
    BibliographyValidationResult,
    DocumentRecord,
    ProjectPaths,
)
from academic_paper_cli.project_manager import get_project_status, project_root


class BibliographyManagerError(ValueError):
    """Raised for bibliographic metadata errors."""


REQUIRED_FIELDS_BY_TYPE = {
    "book": ["title", "authors", "year", "publisher"],
    "journal_article": ["title", "authors", "year", "journal"],
    "book_chapter": ["title", "authors", "year", "publisher"],
    "thesis": ["title", "authors", "year", "publisher"],
    "conference_paper": ["title", "authors", "year"],
    "webpage": ["title", "authors", "year", "url"],
    "generic": ["title", "authors", "year"],
}


def init_bibliography(
    project_name: str,
    projects_root: Path = Path("projects"),
) -> list[BibliographicRecord]:
    """Create bibliography metadata templates for registered documents."""

    paths = _valid_project_paths(project_name, projects_root)
    _ensure_bibliography_paths(paths)
    records: list[BibliographicRecord] = []

    for document in list_documents(project_name, projects_root):
        record_path = _record_path(paths, document.document_id)
        if record_path.exists():
            records.append(_load_record(record_path))
            continue

        record = _template_record(paths, document)
        _write_yaml(record_path, record.to_dict())
        records.append(record)

    _write_state(paths, records)
    return records


def list_bibliography(
    project_name: str,
    projects_root: Path = Path("projects"),
) -> list[BibliographicRecord]:
    """Return all bibliographic records for a project."""

    paths = _valid_project_paths(project_name, projects_root)
    _ensure_bibliography_paths(paths)
    return [_load_record(path) for path in sorted(_bibliography_dir(paths).glob("doc_*.yaml"))]


def show_bibliography_record(
    project_name: str,
    document_id: str,
    projects_root: Path = Path("projects"),
) -> BibliographicRecord:
    """Load one bibliographic record by document ID."""

    paths = _valid_project_paths(project_name, projects_root)
    _ensure_bibliography_paths(paths)
    path = _record_path(paths, document_id)
    if not path.is_file():
        raise BibliographyManagerError(
            f"Bibliographic record does not exist for {document_id}. Run biblio-init first."
        )
    return _load_record(path)


def set_bibliography_record(
    project_name: str,
    document_id: str,
    projects_root: Path = Path("projects"),
    **updates: Any,
) -> BibliographicRecord:
    """Update curated bibliographic fields for one document."""

    paths = _valid_project_paths(project_name, projects_root)
    _ensure_bibliography_paths(paths)
    path = _record_path(paths, document_id)
    if path.exists():
        current = _load_record(path).to_dict()
    else:
        document = _find_document(project_name, document_id, projects_root)
        current = _template_record(paths, document).to_dict()

    for key, value in updates.items():
        if value is None:
            continue
        if key == "verified" and not value:
            continue
        if key == "authors":
            current[key] = [author.to_dict() for author in value]
        elif key == "verified" and value:
            current["metadata_status"] = "verified"
        else:
            current[key] = value

    if not current.get("citation_key"):
        current["citation_key"] = _citation_key(
            current.get("authors", []),
            str(current.get("year", "")),
            str(current.get("title", "")),
            document_id,
        )

    record = BibliographicRecord.from_dict(current)
    _write_yaml(path, record.to_dict())
    _write_state(paths, list_bibliography(project_name, projects_root))
    return record


def validate_bibliography(
    project_name: str,
    projects_root: Path = Path("projects"),
    require_verified: bool = True,
) -> list[BibliographyValidationResult]:
    """Validate bibliographic records for citation readiness."""

    records = list_bibliography(project_name, projects_root)
    return [validate_record(record, require_verified=require_verified) for record in records]


def validate_record(
    record: BibliographicRecord,
    require_verified: bool = True,
) -> BibliographyValidationResult:
    """Validate one bibliographic record."""

    required_fields = REQUIRED_FIELDS_BY_TYPE.get(
        record.item_type,
        REQUIRED_FIELDS_BY_TYPE["generic"],
    )
    missing = [field for field in required_fields if not _has_field(record, field)]
    if require_verified and record.metadata_status != "verified":
        missing.append("metadata_status=verified")
    if not record.citation_key:
        missing.append("citation_key")

    return BibliographyValidationResult(
        document_id=record.document_id,
        citation_key=record.citation_key,
        valid=not missing,
        metadata_status=record.metadata_status,
        missing_fields=missing,
    )


def export_bibliography(
    project_name: str,
    projects_root: Path = Path("projects"),
    export_format: str = "bibtex",
    include_unverified: bool = False,
) -> Path:
    """Export bibliography records as BibTeX or CSL-JSON."""

    paths = _valid_project_paths(project_name, projects_root)
    records = list_bibliography(project_name, projects_root)
    if not include_unverified:
        records = [record for record in records if record.metadata_status == "verified"]

    if export_format == "bibtex":
        output_path = paths.outputs_dir / "reports" / "bibliography.bib"
        output_path.write_text(_to_bibtex(records), encoding="utf-8")
        return output_path
    if export_format == "csl-json":
        output_path = paths.outputs_dir / "reports" / "bibliography.csl.json"
        output_path.write_text(
            json.dumps([_to_csl_json(record) for record in records], indent=2) + "\n",
            encoding="utf-8",
        )
        return output_path

    raise BibliographyManagerError("Export format must be 'bibtex' or 'csl-json'.")


def _template_record(paths: ProjectPaths, document: DocumentRecord) -> BibliographicRecord:
    extracted = _load_extracted_metadata(paths, document.document_id)
    pdf_metadata = extracted.get("pdf_metadata", {}) if extracted else {}
    title = str(pdf_metadata.get("title", "")).strip()
    authors = _authors_from_pdf_metadata(str(pdf_metadata.get("author", "")).strip())
    year = _year_from_pdf_metadata(pdf_metadata)
    identifiers = extracted.get("identifiers", {}) if extracted else {}
    doi = _first_identifier(identifiers.get("doi", []))
    isbn = _first_identifier(identifiers.get("isbn", []))
    citation_key = _citation_key(
        [author.to_dict() for author in authors],
        year,
        title,
        document.document_id,
    )
    return BibliographicRecord(
        document_id=document.document_id,
        title=title,
        authors=authors,
        year=year,
        doi=doi,
        isbn=isbn,
        language=str(extracted.get("language", "") if extracted else ""),
        citation_key=citation_key,
        metadata_status="needs_review",
        notes=(
            "Template created from registered PDF. Verify bibliographic metadata "
            "before using this record in final citations."
        ),
    )


def _load_extracted_metadata(paths: ProjectPaths, document_id: str) -> dict[str, Any]:
    path = paths.dataset_dir / "metadata" / f"{document_id}.json"
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _first_identifier(values: Any) -> str:
    if isinstance(values, list) and values:
        return str(values[0]).strip()
    return ""


def _authors_from_pdf_metadata(author_text: str) -> list[BibliographicAuthor]:
    if not author_text:
        return []
    parts = re.split(r";|\band\b|&", author_text)
    return [
        BibliographicAuthor.from_string(part.strip())
        for part in parts
        if part.strip()
    ]


def _year_from_pdf_metadata(pdf_metadata: dict[str, Any]) -> str:
    for key in ("creationDate", "modDate", "date"):
        value = str(pdf_metadata.get(key, ""))
        match = re.search(r"(19|20)\d{2}", value)
        if match:
            return match.group(0)
    return ""


def _find_document(
    project_name: str,
    document_id: str,
    projects_root: Path,
) -> DocumentRecord:
    for document in list_documents(project_name, projects_root):
        if document.document_id == document_id:
            return document
    raise BibliographyManagerError(f"Unknown document ID: {document_id}")


def _has_field(record: BibliographicRecord, field_name: str) -> bool:
    value = getattr(record, field_name)
    if field_name == "authors":
        return bool(record.authors) and all(author.family for author in record.authors)
    return bool(str(value).strip())


def _record_path(paths: ProjectPaths, document_id: str) -> Path:
    if not re.fullmatch(r"doc_\d+", document_id):
        raise BibliographyManagerError(f"Invalid document ID: {document_id}")
    return _bibliography_dir(paths) / f"{document_id}.yaml"


def _bibliography_dir(paths: ProjectPaths) -> Path:
    return paths.dataset_dir / "bibliography"


def _ensure_bibliography_paths(paths: ProjectPaths) -> None:
    _bibliography_dir(paths).mkdir(parents=True, exist_ok=True)
    (paths.outputs_dir / "reports").mkdir(parents=True, exist_ok=True)


def _valid_project_paths(project_name: str, projects_root: Path) -> ProjectPaths:
    status = get_project_status(project_name, projects_root)
    if not status.valid:
        raise BibliographyManagerError(
            f"Project is missing required structure: {status.root}"
        )
    return ProjectPaths(project_root(projects_root, project_name))


def _load_record(path: Path) -> BibliographicRecord:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise BibliographyManagerError(f"Bibliographic record must be a YAML object: {path}")
    return BibliographicRecord.from_dict(payload)


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )


def _write_state(paths: ProjectPaths, records: list[BibliographicRecord]) -> None:
    state_path = _bibliography_dir(paths) / "bibliography_state.json"
    payload = {
        "version": 1,
        "updated_at": _utc_now_iso(),
        "record_count": len(records),
        "verified_count": sum(
            1 for record in records if record.metadata_status == "verified"
        ),
    }
    state_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _citation_key(
    authors: list[dict[str, str]],
    year: str,
    title: str,
    fallback: str,
) -> str:
    family = ""
    if authors:
        family = str(authors[0].get("family", "")).strip()
    parts = [family, year, title.split()[0] if title else ""]
    key = "_".join(_slug(part) for part in parts if part)
    return key or fallback


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", value.strip().lower()).strip("_")
    return slug


def _to_bibtex(records: list[BibliographicRecord]) -> str:
    entries = [_bibtex_entry(record) for record in records]
    return "\n\n".join(entries).strip() + ("\n" if entries else "")


def _bibtex_entry(record: BibliographicRecord) -> str:
    entry_type = {
        "book": "book",
        "journal_article": "article",
        "book_chapter": "incollection",
        "thesis": "phdthesis",
        "conference_paper": "inproceedings",
        "webpage": "misc",
    }.get(record.item_type, "misc")
    fields = {
        "title": record.title,
        "author": " and ".join(
            f"{author.family}, {author.given}".strip().strip(",")
            for author in record.authors
        ),
        "year": record.year,
        "publisher": record.publisher,
        "address": record.place,
        "journal": record.journal,
        "volume": record.volume,
        "number": record.issue,
        "pages": record.pages,
        "doi": record.doi,
        "isbn": record.isbn,
        "url": record.url,
    }
    body = [
        f"  {field} = {{{value}}}"
        for field, value in fields.items()
        if value
    ]
    return f"@{entry_type}{{{record.citation_key},\n" + ",\n".join(body) + "\n}"


def _to_csl_json(record: BibliographicRecord) -> dict[str, Any]:
    return {
        "id": record.citation_key,
        "type": _csl_type(record.item_type),
        "title": record.title,
        "author": [
            {"family": author.family, "given": author.given}
            for author in record.authors
        ],
        "issued": {"date-parts": [[int(record.year)]]} if record.year.isdigit() else {},
        "publisher": record.publisher,
        "publisher-place": record.place,
        "container-title": record.journal,
        "volume": record.volume,
        "issue": record.issue,
        "page": record.pages,
        "DOI": record.doi,
        "ISBN": record.isbn,
        "URL": record.url,
        "language": record.language,
    }


def _csl_type(item_type: str) -> str:
    return {
        "journal_article": "article-journal",
        "book_chapter": "chapter",
        "conference_paper": "paper-conference",
        "thesis": "thesis",
        "webpage": "webpage",
    }.get(item_type, item_type)


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()
