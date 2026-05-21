"""Module 2: PDF registration and dataset listing."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from academic_paper_cli.models import AddPdfResult, DocumentRecord, ProjectPaths
from academic_paper_cli.project_manager import get_project_status, project_root


class DatasetManagerError(ValueError):
    """Raised for dataset manager validation errors."""


def add_pdf(
    project_name: str,
    source_file: Path,
    projects_root: Path = Path("projects"),
) -> AddPdfResult:
    """Copy a PDF into the project dataset and register it in ingestion state."""

    paths = _valid_project_paths(project_name, projects_root)
    source_path = source_file.expanduser().resolve()
    _validate_pdf_source(source_path)

    state_path = paths.state_dir / "ingestion_state.json"
    state = _load_ingestion_state(state_path)
    checksum = _sha256(source_path)

    duplicate = _find_document_by_checksum(state, checksum)
    if duplicate is not None:
        return AddPdfResult(record=duplicate, added=False, duplicate_of=duplicate.document_id)

    document_id = _next_document_id(state)
    stored_filename = f"{document_id}__{_safe_filename(source_path.name)}"
    stored_path = paths.dataset_dir / "pdf" / stored_filename
    shutil.copy2(source_path, stored_path)

    record = DocumentRecord(
        document_id=document_id,
        original_filename=source_path.name,
        source_path=str(source_path),
        stored_path=str(stored_path),
        sha256=checksum,
        added_at=_utc_now_iso(),
    )

    state.setdefault("documents", {})[document_id] = record.to_dict()
    state["updated_at"] = _utc_now_iso()
    _write_json(state_path, state)

    return AddPdfResult(record=record, added=True)


def list_documents(
    project_name: str,
    projects_root: Path = Path("projects"),
) -> list[DocumentRecord]:
    """Return registered documents sorted by document ID."""

    paths = _valid_project_paths(project_name, projects_root)
    state = _load_ingestion_state(paths.state_dir / "ingestion_state.json")
    documents = state.get("documents", {})
    return [
        DocumentRecord.from_dict(payload)
        for _, payload in sorted(documents.items(), key=lambda item: item[0])
    ]


def _valid_project_paths(project_name: str, projects_root: Path) -> ProjectPaths:
    status = get_project_status(project_name, projects_root)
    if not status.valid:
        raise DatasetManagerError(
            f"Project is missing required Module 1 structure: {status.root}"
        )
    return ProjectPaths(project_root(projects_root, project_name))


def _validate_pdf_source(source_path: Path) -> None:
    if not source_path.is_file():
        raise DatasetManagerError(f"PDF file does not exist: {source_path}")
    if source_path.suffix.lower() != ".pdf":
        raise DatasetManagerError(f"Source file must have a .pdf extension: {source_path}")


def _load_ingestion_state(state_path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise DatasetManagerError(f"Missing ingestion state file: {state_path}") from error
    except json.JSONDecodeError as error:
        raise DatasetManagerError(f"Invalid ingestion state JSON: {state_path}") from error

    if not isinstance(payload, dict):
        raise DatasetManagerError(f"Ingestion state must be a JSON object: {state_path}")
    if "documents" not in payload or not isinstance(payload["documents"], dict):
        payload["documents"] = {}
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _find_document_by_checksum(
    state: dict[str, Any],
    checksum: str,
) -> DocumentRecord | None:
    for payload in state.get("documents", {}).values():
        if payload.get("sha256") == checksum:
            return DocumentRecord.from_dict(payload)
    return None


def _next_document_id(state: dict[str, Any]) -> str:
    max_number = 0
    for document_id in state.get("documents", {}):
        match = re.fullmatch(r"doc_(\d+)", document_id)
        if match:
            max_number = max(max_number, int(match.group(1)))
    return f"doc_{max_number + 1:04d}"


def _safe_filename(filename: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", filename.strip())
    safe = safe.strip("._")
    return safe or "source.pdf"


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()
