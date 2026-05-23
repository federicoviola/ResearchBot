"""Module 5b: grounded query generation from retrieved dataset chunks."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from academic_paper_cli.llm_client import LLMClient, LLMSettings, client_from_settings
from academic_paper_cli.models import ProjectPaths, QueryResult, RetrievalResult
from academic_paper_cli.project_manager import get_project_status, project_root
from academic_paper_cli.retrieval_engine import retrieve_chunks


class QueryEngineError(ValueError):
    """Raised for grounded query generation errors."""


def query_dataset(
    project_name: str,
    query: str,
    projects_root: Path = Path("projects"),
    top_k: int | None = None,
    context_chars: int | None = None,
    dry_run: bool = False,
    llm_client: LLMClient | None = None,
) -> QueryResult:
    """Retrieve corpus context, compose a closed prompt, and query an LLM."""

    if not query.strip():
        raise QueryEngineError("Query cannot be empty.")

    paths = _valid_project_paths(project_name, projects_root)
    config = _load_project_config(paths)
    llm_settings = _llm_settings(config)
    resolved_context_chars = _context_chars(config, context_chars)
    retrieval_results = retrieve_chunks(project_name, query, projects_root, top_k)
    if not retrieval_results:
        unsupported = _unsupported_answer(config)
        return _save_query_result(
            paths=paths,
            result=QueryResult(
                project_name=project_name,
                query=query,
                answer=unsupported,
                retrieval_results=[],
                provider=llm_settings.provider,
                model=llm_settings.model,
                dry_run=dry_run,
                context_chars=resolved_context_chars,
            ),
            messages=[],
        )

    messages = _compose_messages(paths, config, query, retrieval_results, resolved_context_chars)
    if dry_run:
        answer = "DRY RUN: no LLM call was made. Review the saved prompt and retrieved sources."
    else:
        client = llm_client or client_from_settings(llm_settings)
        answer = client.complete(messages)
    return _save_query_result(
        paths=paths,
        result=QueryResult(
            project_name=project_name,
            query=query,
            answer=answer,
            retrieval_results=retrieval_results,
            provider=llm_settings.provider,
            model=llm_settings.model,
            dry_run=dry_run,
            context_chars=resolved_context_chars,
        ),
        messages=messages,
    )


def _compose_messages(
    paths: ProjectPaths,
    config: dict[str, Any],
    query: str,
    retrieval_results: list[RetrievalResult],
    context_chars: int,
) -> list[dict[str, str]]:
    system_prompt = _read_text(paths.config_dir / "system_prompt.md")
    writing_style = _read_text(paths.config_dir / "writing_style.md")
    citation_style = _read_text(paths.config_dir / "citation_style.yaml")
    project_summary = yaml.safe_dump(config, sort_keys=False, allow_unicode=False)
    context = _format_retrieved_context(retrieval_results, context_chars=context_chars)
    unsupported = _unsupported_answer(config)

    system_content = "\n\n".join(
        [
            system_prompt,
            "# Grounding Rules",
            "- Use only the retrieved dataset context in the user message.",
            "- Do not use outside knowledge, even if it seems relevant.",
            "- Every substantive claim must cite one or more source IDs.",
            "- Do not invent references, authors, dates, or bibliography entries.",
            f"- If the retrieved context is insufficient, answer exactly this policy in your own sentence: {unsupported}",
        ]
    )
    user_content = "\n\n".join(
        [
            "# Project Configuration",
            project_summary,
            "# Writing Style",
            writing_style,
            "# Citation Style",
            citation_style,
            "# Retrieved Dataset Context",
            context,
            "# User Question",
            query,
            "# Required Answer Format",
            "Answer concisely. Include a 'Sources' section listing the chunk IDs used.",
        ]
    )
    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]


def _format_retrieved_context(
    results: list[RetrievalResult],
    *,
    context_chars: int = 1200,
) -> str:
    blocks = []
    for result in results:
        chunk = result.chunk
        chunk_text = _limit_context_text(chunk.text, context_chars)
        source = " | ".join(
            value
            for value in [
                chunk.chunk_id,
                chunk.document_id,
                chunk.title,
                "; ".join(chunk.authors),
                chunk.year,
            ]
            if value
        )
        blocks.append(
            "\n".join(
                [
                    f"[SOURCE {result.rank}] {source}",
                    f"score: {result.score:.6f}",
                    chunk_text,
                ]
            )
        )
    return "\n\n---\n\n".join(blocks)


def _limit_context_text(text: str, context_chars: int) -> str:
    clean_text = text.strip()
    if context_chars <= 0 or len(clean_text) <= context_chars:
        return clean_text
    truncated = clean_text[:context_chars].rstrip()
    return (
        f"{truncated}\n\n"
        f"[Context truncated to {context_chars} characters from {len(clean_text)} total.]"
    )


def _save_query_result(
    paths: ProjectPaths,
    result: QueryResult,
    messages: list[dict[str, str]],
) -> QueryResult:
    logs_dir = paths.outputs_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    run_id = _run_id()
    prompt_path = logs_dir / f"{run_id}_prompt.json"
    response_path = logs_dir / f"{run_id}_response.json"
    prompt_path.write_text(
        json.dumps({"messages": messages}, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    response_payload = {
        "project_name": result.project_name,
        "query": result.query,
        "answer": result.answer,
        "provider": result.provider,
        "model": result.model,
        "dry_run": result.dry_run,
        "context_chars": result.context_chars,
        "sources": [
            {
                "rank": retrieval.rank,
                "score": retrieval.score,
                "chunk_id": retrieval.chunk.chunk_id,
                "document_id": retrieval.chunk.document_id,
                "title": retrieval.chunk.title,
                "authors": retrieval.chunk.authors,
                "year": retrieval.chunk.year,
            }
            for retrieval in result.retrieval_results
        ],
    }
    response_path.write_text(
        json.dumps(response_payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    return QueryResult(
        project_name=result.project_name,
        query=result.query,
        answer=result.answer,
        retrieval_results=result.retrieval_results,
        provider=result.provider,
        model=result.model,
        prompt_path=str(prompt_path),
        response_path=str(response_path),
        dry_run=result.dry_run,
        context_chars=result.context_chars,
    )


def _context_chars(config: dict[str, Any], override: int | None) -> int:
    if override is not None:
        if override < 0:
            raise QueryEngineError("--context-chars must be zero or a positive integer.")
        return override
    retrieval = config.get("retrieval", {}) if isinstance(config, dict) else {}
    value = retrieval.get("context_chars", 1200) if isinstance(retrieval, dict) else 1200
    context_chars = int(value)
    if context_chars < 0:
        raise QueryEngineError("retrieval.context_chars must be zero or a positive integer.")
    return context_chars


def _llm_settings(config: dict[str, Any]) -> LLMSettings:
    llm = config.get("llm", {}) if isinstance(config, dict) else {}
    return LLMSettings(
        provider=str(llm.get("provider", "openai_compatible")),
        base_url=str(llm.get("base_url", "http://localhost:11434/v1")),
        model=str(llm.get("model", "configure-me")),
        api_key_env=str(llm.get("api_key_env", "OPENAI_API_KEY")),
        temperature=float(llm.get("temperature", 0.2)),
        max_tokens=int(llm.get("max_tokens", 1800)),
        timeout_seconds=int(llm.get("timeout_seconds", 120)),
    )


def _unsupported_answer(config: dict[str, Any]) -> str:
    grounding = config.get("grounding", {}) if isinstance(config, dict) else {}
    return str(
        grounding.get(
            "unsupported_answer",
            "The dataset does not contain enough information to answer this without unsupported claims.",
        )
    )


def _load_project_config(paths: ProjectPaths) -> dict[str, Any]:
    config_path = paths.config_dir / "project.yaml"
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return payload if isinstance(payload, dict) else {}


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _valid_project_paths(project_name: str, projects_root: Path) -> ProjectPaths:
    status = get_project_status(project_name, projects_root)
    if not status.valid:
        raise QueryEngineError(f"Project is missing required structure: {status.root}")
    return ProjectPaths(project_root(projects_root, project_name))


def _run_id() -> str:
    return "query_" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
