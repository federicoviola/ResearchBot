"""Module 3: PDF text and metadata extraction."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from academic_paper_cli.models import DocumentRecord, IngestionResult, ProjectPaths
from academic_paper_cli.project_manager import get_project_status, project_root


class PdfProcessorError(ValueError):
    """Raised for PDF ingestion validation errors."""


def ingest_project(
    project_name: str,
    projects_root: Path = Path("projects"),
    force: bool = False,
) -> list[IngestionResult]:
    """Extract text and metadata for registered PDFs in a project."""

    paths = _valid_project_paths(project_name, projects_root)
    state_path = paths.state_dir / "ingestion_state.json"
    state = _load_ingestion_state(state_path)
    documents = state.get("documents", {})

    results: list[IngestionResult] = []
    for document_id, payload in sorted(documents.items(), key=lambda item: item[0]):
        record = DocumentRecord.from_dict(payload)
        if record.status == "ingested" and not force:
            results.append(_result_from_record(record, skipped=True))
            continue

        result = _ingest_document(paths, record)
        results.append(result)

        updated_payload = dict(payload)
        updated_payload["status"] = result.status
        updated_payload["ingested_at"] = _utc_now_iso()
        updated_payload["text_path"] = result.text_path
        updated_payload["metadata_path"] = result.metadata_path
        updated_payload["page_count"] = result.page_count
        updated_payload["character_count"] = result.character_count
        updated_payload["word_count"] = result.word_count
        if result.error:
            updated_payload["error"] = result.error
        else:
            updated_payload.pop("error", None)

        documents[document_id] = updated_payload

    state["documents"] = documents
    state["updated_at"] = _utc_now_iso()
    _write_json(state_path, state)
    return results


def _ingest_document(paths: ProjectPaths, record: DocumentRecord) -> IngestionResult:
    source_pdf = Path(record.stored_path)
    if not source_pdf.is_file():
        return IngestionResult(
            document_id=record.document_id,
            original_filename=record.original_filename,
            status="ingestion_failed",
            text_path=None,
            metadata_path=None,
            error=f"Stored PDF is missing: {source_pdf}",
        )

    try:
        import fitz
    except ImportError as error:
        raise PdfProcessorError(
            "PyMuPDF is required for ingestion. Install dependencies with "
            "`python3 -m pip install -r requirements.txt`."
        ) from error

    try:
        with fitz.open(source_pdf) as pdf:
            page_texts: list[str] = []
            for page_index, page in enumerate(pdf, start=1):
                page_text = page.get_text("text").strip()
                page_texts.append(f"\n\n--- Page {page_index} ---\n\n{page_text}")

            text = "".join(page_texts).strip() + "\n"
            metadata = _metadata_from_pdf(pdf, record, source_pdf, text)
    except Exception as error:
        return IngestionResult(
            document_id=record.document_id,
            original_filename=record.original_filename,
            status="ingestion_failed",
            text_path=None,
            metadata_path=None,
            error=str(error),
        )

    text_path = paths.dataset_dir / "txt" / f"{record.document_id}.txt"
    metadata_path = paths.dataset_dir / "metadata" / f"{record.document_id}.json"
    text_path.write_text(text, encoding="utf-8")
    _write_json(metadata_path, metadata)

    return IngestionResult(
        document_id=record.document_id,
        original_filename=record.original_filename,
        status="ingested",
        text_path=str(text_path),
        metadata_path=str(metadata_path),
        page_count=metadata["page_count"],
        character_count=metadata["extraction"]["character_count"],
        word_count=metadata["extraction"]["word_count"],
    )


def _metadata_from_pdf(
    pdf: Any,
    record: DocumentRecord,
    source_pdf: Path,
    text: str,
) -> dict[str, Any]:
    raw_metadata = dict(pdf.metadata or {})
    cleaned_metadata = {
        str(key): value for key, value in raw_metadata.items() if value not in (None, "")
    }
    return {
        "document_id": record.document_id,
        "original_filename": record.original_filename,
        "stored_path": str(source_pdf),
        "sha256": record.sha256,
        "page_count": int(pdf.page_count),
        "pdf_metadata": cleaned_metadata,
        "identifiers": _extract_identifiers(text, cleaned_metadata),
        "extraction": {
            "extracted_at": _utc_now_iso(),
            "tool": "PyMuPDF",
            "character_count": len(text),
            "word_count": len(text.split()),
        },
    }


def _result_from_record(record: DocumentRecord, skipped: bool) -> IngestionResult:
    status = "skipped" if skipped else record.status
    return IngestionResult(
        document_id=record.document_id,
        original_filename=record.original_filename,
        status=status,
        text_path=None,
        metadata_path=None,
    )


def _extract_identifiers(text: str, pdf_metadata: dict[str, Any]) -> dict[str, list[str]]:
    haystack = "\n".join([text, *[str(value) for value in pdf_metadata.values()]])
    return {
        "doi": _unique(_extract_dois(haystack)),
        "isbn": _unique(_extract_isbns(haystack)),
    }


def _extract_dois(text: str) -> list[str]:
    pattern = re.compile(r"\b10\.\d{4,9}/[^\s\"<>]+", re.IGNORECASE)
    dois = []
    for match in pattern.finditer(text):
        doi = match.group(0).rstrip(".,;:)]}")
        dois.append(doi)
    return dois


def _extract_isbns(text: str) -> list[str]:
    pattern = re.compile(
        r"\b(?:ISBN(?:-1[03])?:?\s*)?"
        r"(?=(?:[0-9Xx][ -]?){10,17}\b)"
        r"(?:97[89][ -]?)?[0-9][0-9 -]{8,}[0-9Xx]\b",
        re.IGNORECASE,
    )
    isbns = []
    for match in pattern.finditer(text):
        isbn = re.sub(r"[^0-9Xx]", "", match.group(0))
        if len(isbn) in (10, 13):
            isbns.append(isbn)
    return isbns


def _unique(values: list[str]) -> list[str]:
    seen = set()
    unique_values = []
    for value in values:
        normalized = value.lower()
        if normalized not in seen:
            unique_values.append(value)
            seen.add(normalized)
    return unique_values


def _valid_project_paths(project_name: str, projects_root: Path) -> ProjectPaths:
    status = get_project_status(project_name, projects_root)
    if not status.valid:
        raise PdfProcessorError(
            f"Project is missing required structure: {status.root}"
        )
    return ProjectPaths(project_root(projects_root, project_name))


def _load_ingestion_state(state_path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise PdfProcessorError(f"Missing ingestion state file: {state_path}") from error
    except json.JSONDecodeError as error:
        raise PdfProcessorError(f"Invalid ingestion state JSON: {state_path}") from error

    if not isinstance(payload, dict):
        raise PdfProcessorError(f"Ingestion state must be a JSON object: {state_path}")
    if "documents" not in payload or not isinstance(payload["documents"], dict):
        payload["documents"] = {}
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()
