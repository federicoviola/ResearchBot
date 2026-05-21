"""Module 5a: local dataset retrieval over indexed chunks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from academic_paper_cli.index_builder import _hashing_embedding
from academic_paper_cli.models import ChunkRecord, ProjectPaths, RetrievalResult
from academic_paper_cli.project_manager import get_project_status, project_root


class RetrievalEngineError(ValueError):
    """Raised for local retrieval errors."""


def retrieve_chunks(
    project_name: str,
    query: str,
    projects_root: Path = Path("projects"),
    top_k: int | None = None,
) -> list[RetrievalResult]:
    """Retrieve the most relevant indexed chunks for a query."""

    if not query.strip():
        raise RetrievalEngineError("Query cannot be empty.")

    paths = _valid_project_paths(project_name, projects_root)
    state = _load_index_state(paths)
    if state.get("status") != "built":
        raise RetrievalEngineError("Index is not built. Run build-index first.")

    chunks_path = Path(str(state.get("chunks_path", "")))
    embeddings_path = Path(str(state.get("embeddings_path", "")))
    if not chunks_path.is_file() or not embeddings_path.is_file():
        raise RetrievalEngineError("Index artifacts are missing. Run build-index --force.")

    embedding_backend = str(state.get("embedding_backend", ""))
    if embedding_backend != "hashing":
        raise RetrievalEngineError(f"Unsupported embedding backend: {embedding_backend}")
    dimensions = int(state.get("embedding_dimensions", 256))
    resolved_top_k = _resolve_top_k(paths, top_k)

    chunks = _load_chunks(chunks_path)
    embeddings = _load_embeddings(embeddings_path)
    query_embedding = _hashing_embedding(query, dimensions)

    ranked: list[RetrievalResult] = []
    for chunk_id, embedding in embeddings.items():
        chunk = chunks.get(chunk_id)
        if not chunk:
            continue
        ranked.append(
            RetrievalResult(
                chunk=chunk,
                score=_dot(query_embedding, embedding),
                rank=0,
            )
        )

    ranked.sort(key=lambda result: result.score, reverse=True)
    return [
        RetrievalResult(chunk=result.chunk, score=result.score, rank=index)
        for index, result in enumerate(ranked[:resolved_top_k], start=1)
    ]


def _load_chunks(path: Path) -> dict[str, ChunkRecord]:
    chunks = {}
    for row in _read_jsonl(path):
        chunk = ChunkRecord.from_dict(row)
        if chunk.chunk_id:
            chunks[chunk.chunk_id] = chunk
    return chunks


def _load_embeddings(path: Path) -> dict[str, list[float]]:
    embeddings = {}
    for row in _read_jsonl(path):
        chunk_id = str(row.get("chunk_id", "")).strip()
        embedding = row.get("embedding", [])
        if chunk_id and isinstance(embedding, list):
            embeddings[chunk_id] = [float(value) for value in embedding]
    return embeddings


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _dot(left: list[float], right: list[float]) -> float:
    return round(sum(a * b for a, b in zip(left, right)), 6)


def _resolve_top_k(paths: ProjectPaths, top_k: int | None) -> int:
    if top_k is not None:
        if top_k <= 0:
            raise RetrievalEngineError("--top-k must be greater than zero.")
        return top_k
    config = _load_project_config(paths)
    retrieval = config.get("retrieval", {}) if isinstance(config, dict) else {}
    configured = int(retrieval.get("top_k", 8))
    return configured if configured > 0 else 8


def _load_project_config(paths: ProjectPaths) -> dict[str, Any]:
    config_path = paths.config_dir / "project.yaml"
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return payload if isinstance(payload, dict) else {}


def _load_index_state(paths: ProjectPaths) -> dict[str, Any]:
    state_path = paths.state_dir / "index_state.json"
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise RetrievalEngineError(f"Missing index state file: {state_path}") from error
    except json.JSONDecodeError as error:
        raise RetrievalEngineError(f"Invalid index state JSON: {state_path}") from error
    if not isinstance(payload, dict):
        raise RetrievalEngineError(f"Index state must be a JSON object: {state_path}")
    return payload


def _valid_project_paths(project_name: str, projects_root: Path) -> ProjectPaths:
    status = get_project_status(project_name, projects_root)
    if not status.valid:
        raise RetrievalEngineError(f"Project is missing required structure: {status.root}")
    return ProjectPaths(project_root(projects_root, project_name))
