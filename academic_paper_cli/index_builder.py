"""Module 4: local corpus indexing.

The index is a derived artifact from the closed project dataset. It stores
auditable chunks plus lightweight local embeddings for later retrieval modules.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from academic_paper_cli.bibliography_manager import list_bibliography
from academic_paper_cli.models import (
    BibliographicRecord,
    ChunkRecord,
    IndexBuildResult,
    IndexStatus,
    ProjectPaths,
)
from academic_paper_cli.project_manager import get_project_status, project_root


class IndexBuilderError(ValueError):
    """Raised for index build and status errors."""


def build_index(
    project_name: str,
    projects_root: Path = Path("projects"),
    force: bool = False,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    embedding_backend: str = "hashing",
    embedding_dimensions: int = 256,
) -> IndexBuildResult:
    """Build a local chunk and embedding index from extracted text files."""

    paths = _valid_project_paths(project_name, projects_root)
    index_dir = paths.dataset_dir / "index"
    chunks_path = index_dir / "chunks.jsonl"
    embeddings_path = index_dir / "embeddings.jsonl"
    state_path = paths.state_dir / "index_state.json"

    if chunks_path.exists() and embeddings_path.exists() and not force:
        raise IndexBuilderError("Index already exists. Use --force to rebuild it.")

    config = _load_project_config(paths)
    retrieval = config.get("retrieval", {}) if isinstance(config, dict) else {}
    resolved_chunk_size = _positive_int(
        chunk_size,
        retrieval.get("chunk_size"),
        default=900,
    )
    resolved_chunk_overlap = _non_negative_int(
        chunk_overlap,
        retrieval.get("chunk_overlap"),
        default=150,
    )
    if resolved_chunk_overlap >= resolved_chunk_size:
        raise IndexBuilderError("chunk_overlap must be smaller than chunk_size.")
    if embedding_backend != "hashing":
        raise IndexBuilderError("Only the local 'hashing' embedding backend is implemented.")

    bibliography = {
        record.document_id: record
        for record in list_bibliography(project_name, projects_root)
    }
    chunks = _chunk_texts(paths, bibliography, resolved_chunk_size, resolved_chunk_overlap)
    if not chunks:
        raise IndexBuilderError("No extracted text files found. Run ingest first.")

    index_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(chunks_path, [chunk.to_dict() for chunk in chunks])
    _write_jsonl(
        embeddings_path,
        [
            {
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "embedding": _hashing_embedding(chunk.text, embedding_dimensions),
            }
            for chunk in chunks
        ],
    )

    built_at = _utc_now_iso()
    state = {
        "status": "built",
        "project_name": project_name,
        "document_count": len({chunk.document_id for chunk in chunks}),
        "chunk_count": len(chunks),
        "chunk_size": resolved_chunk_size,
        "chunk_overlap": resolved_chunk_overlap,
        "embedding_backend": embedding_backend,
        "embedding_dimensions": embedding_dimensions,
        "chunks_path": str(chunks_path),
        "embeddings_path": str(embeddings_path),
        "built_at": built_at,
    }
    _write_json(state_path, state)

    return IndexBuildResult(
        project_name=project_name,
        document_count=state["document_count"],
        chunk_count=state["chunk_count"],
        embedding_backend=embedding_backend,
        embedding_dimensions=embedding_dimensions,
        chunks_path=str(chunks_path),
        embeddings_path=str(embeddings_path),
        status_path=str(state_path),
        built_at=built_at,
    )


def get_index_status(
    project_name: str,
    projects_root: Path = Path("projects"),
) -> IndexStatus:
    """Return current index state for a project."""

    paths = _valid_project_paths(project_name, projects_root)
    state_path = paths.state_dir / "index_state.json"
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise IndexBuilderError(f"Missing index state file: {state_path}") from error
    except json.JSONDecodeError as error:
        raise IndexBuilderError(f"Invalid index state JSON: {state_path}") from error

    if not isinstance(payload, dict):
        raise IndexBuilderError(f"Index state must be a JSON object: {state_path}")
    status = str(payload.get("status", "not_built"))
    chunks_path = str(payload.get("chunks_path", ""))
    embeddings_path = str(payload.get("embeddings_path", ""))
    if status == "built" and (
        not chunks_path
        or not embeddings_path
        or not Path(chunks_path).is_file()
        or not Path(embeddings_path).is_file()
    ):
        status = "stale"

    return IndexStatus(
        project_name=project_name,
        status=status,
        document_count=int(payload.get("document_count", 0)),
        chunk_count=int(payload.get("chunk_count", 0)),
        embedding_backend=str(payload.get("embedding_backend", "")),
        embedding_dimensions=int(payload.get("embedding_dimensions", 0)),
        chunks_path=chunks_path,
        embeddings_path=embeddings_path,
        built_at=str(payload.get("built_at", "")),
        message=str(payload.get("message", "")),
    )


def _chunk_texts(
    paths: ProjectPaths,
    bibliography: dict[str, BibliographicRecord],
    chunk_size: int,
    chunk_overlap: int,
) -> list[ChunkRecord]:
    chunks: list[ChunkRecord] = []
    for text_path in sorted((paths.dataset_dir / "txt").glob("doc_*.txt")):
        document_id = text_path.stem
        text = _normalize_text(text_path.read_text(encoding="utf-8"))
        words = text.split()
        if not words:
            continue
        record = bibliography.get(document_id)
        step = chunk_size - chunk_overlap
        chunk_index = 0
        for start in range(0, len(words), step):
            end = min(start + chunk_size, len(words))
            chunk_words = words[start:end]
            if not chunk_words:
                continue
            chunk_index += 1
            chunks.append(
                ChunkRecord(
                    chunk_id=f"{document_id}_chunk_{chunk_index:04d}",
                    document_id=document_id,
                    chunk_index=chunk_index,
                    text=" ".join(chunk_words),
                    start_word=start,
                    end_word=end,
                    word_count=len(chunk_words),
                    title=record.title if record else "",
                    authors=_author_strings(record) if record else [],
                    year=record.year if record else "",
                    citation_key=record.citation_key if record else "",
                )
            )
            if end == len(words):
                break
    return chunks


def _hashing_embedding(text: str, dimensions: int) -> list[float]:
    vector = [0.0] * dimensions
    for token in _tokens(text):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[bucket] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if not norm:
        return vector
    return [round(value / norm, 6) for value in vector]


def _tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-zÀ-ÿ0-9_]+", text.lower())


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _author_strings(record: BibliographicRecord | None) -> list[str]:
    if not record:
        return []
    return [
        f"{author.family}, {author.given}".strip().strip(",")
        for author in record.authors
        if author.family
    ]


def _load_project_config(paths: ProjectPaths) -> dict[str, Any]:
    config_path = paths.config_dir / "project.yaml"
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return payload if isinstance(payload, dict) else {}


def _positive_int(*values: Any, default: int) -> int:
    for value in values:
        if value is None:
            continue
        parsed = int(value)
        if parsed <= 0:
            raise IndexBuilderError("chunk_size must be greater than zero.")
        return parsed
    return default


def _non_negative_int(*values: Any, default: int) -> int:
    for value in values:
        if value is None:
            continue
        parsed = int(value)
        if parsed < 0:
            raise IndexBuilderError("chunk_overlap cannot be negative.")
        return parsed
    return default


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=True, sort_keys=True) for row in rows)
        + "\n",
        encoding="utf-8",
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _valid_project_paths(project_name: str, projects_root: Path) -> ProjectPaths:
    status = get_project_status(project_name, projects_root)
    if not status.valid:
        raise IndexBuilderError(f"Project is missing required structure: {status.root}")
    return ProjectPaths(project_root(projects_root, project_name))


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()
