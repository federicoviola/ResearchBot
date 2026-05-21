"""Module 6: grounded academic outline generation."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from academic_paper_cli.llm_client import LLMClient, LLMSettings, client_from_settings
from academic_paper_cli.models import OutlineResult, ProjectPaths, RetrievalResult
from academic_paper_cli.project_manager import get_project_status, project_root
from academic_paper_cli.query_engine import _format_retrieved_context
from academic_paper_cli.retrieval_engine import retrieve_chunks


class OutlineGeneratorError(ValueError):
    """Raised for grounded outline generation errors."""


def generate_outline(
    project_name: str,
    skill_name: str,
    projects_root: Path = Path("projects"),
    topic: str | None = None,
    top_k: int | None = None,
    dry_run: bool = False,
    llm_client: LLMClient | None = None,
) -> OutlineResult:
    """Generate and save a source-mapped academic paper outline."""

    paths = _valid_project_paths(project_name, projects_root)
    config = _load_project_config(paths)
    resolved_topic = _resolve_topic(config, topic)
    skill_text = _load_skill(paths, skill_name)
    llm_settings = _llm_settings(config)
    retrieval_results = retrieve_chunks(project_name, resolved_topic, projects_root, top_k)
    if not retrieval_results:
        raise OutlineGeneratorError("No retrieved context available. Run build-index or adjust topic.")

    messages = _compose_outline_messages(
        paths=paths,
        config=config,
        topic=resolved_topic,
        skill_name=skill_name,
        skill_text=skill_text,
        retrieval_results=retrieval_results,
    )
    if dry_run:
        outline = "DRY RUN: no LLM call was made. Review the saved outline prompt and sources."
    else:
        client = llm_client or client_from_settings(llm_settings)
        outline = client.complete(messages)

    return _save_outline_result(
        paths=paths,
        result=OutlineResult(
            project_name=project_name,
            topic=resolved_topic,
            skill_name=skill_name,
            outline=outline,
            retrieval_results=retrieval_results,
            provider=llm_settings.provider,
            model=llm_settings.model,
            dry_run=dry_run,
        ),
        messages=messages,
    )


def _compose_outline_messages(
    paths: ProjectPaths,
    config: dict[str, Any],
    topic: str,
    skill_name: str,
    skill_text: str,
    retrieval_results: list[RetrievalResult],
) -> list[dict[str, str]]:
    system_prompt = _read_text(paths.config_dir / "system_prompt.md")
    writing_style = _read_text(paths.config_dir / "writing_style.md")
    citation_style = _read_text(paths.config_dir / "citation_style.yaml")
    project_summary = yaml.safe_dump(config, sort_keys=False, allow_unicode=False)
    context = _format_retrieved_context(retrieval_results)
    unsupported = _unsupported_answer(config)

    system_content = "\n\n".join(
        [
            system_prompt,
            "# Grounding Rules",
            "- Build the outline only from the retrieved dataset context.",
            "- Do not use outside knowledge, even if it seems relevant.",
            "- Every section must list supporting chunk IDs.",
            "- Do not invent references, authors, dates, or bibliography entries.",
            f"- If evidence is insufficient, say so explicitly: {unsupported}",
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
            f"# Selected Skill: {skill_name}",
            skill_text,
            "# Retrieved Dataset Context",
            context,
            "# Outline Topic",
            topic,
            "# Required Output",
            "\n".join(
                [
                    "Produce a structured academic paper outline in Markdown.",
                    "For every major section include: purpose, key claims/questions, and supporting chunk IDs.",
                    "Include a final 'Evidence Gaps' section for weak, partial, or absent support.",
                    "Do not include bibliography entries outside the retrieved dataset.",
                ]
            ),
        ]
    )
    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]


def _save_outline_result(
    paths: ProjectPaths,
    result: OutlineResult,
    messages: list[dict[str, str]],
) -> OutlineResult:
    run_id = _run_id()
    outlines_dir = paths.outputs_dir / "outlines"
    logs_dir = paths.outputs_dir / "logs"
    outlines_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    output_path = outlines_dir / f"{run_id}_{_slug(result.skill_name)}.md"
    prompt_path = logs_dir / f"{run_id}_outline_prompt.json"
    response_path = logs_dir / f"{run_id}_outline_response.json"

    output_path.write_text(result.outline.strip() + "\n", encoding="utf-8")
    prompt_path.write_text(
        json.dumps({"messages": messages}, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    response_path.write_text(
        json.dumps(
            {
                "project_name": result.project_name,
                "topic": result.topic,
                "skill_name": result.skill_name,
                "outline": result.outline,
                "provider": result.provider,
                "model": result.model,
                "dry_run": result.dry_run,
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
            },
            indent=2,
            ensure_ascii=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return OutlineResult(
        project_name=result.project_name,
        topic=result.topic,
        skill_name=result.skill_name,
        outline=result.outline,
        retrieval_results=result.retrieval_results,
        provider=result.provider,
        model=result.model,
        output_path=str(output_path),
        prompt_path=str(prompt_path),
        response_path=str(response_path),
        dry_run=result.dry_run,
    )


def _load_skill(paths: ProjectPaths, skill_name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", skill_name):
        raise OutlineGeneratorError("Skill name may only contain letters, numbers, underscores, and hyphens.")
    skill_path = paths.skills_dir / f"{skill_name}.md"
    if not skill_path.is_file():
        raise OutlineGeneratorError(f"Skill does not exist: {skill_path}")
    return skill_path.read_text(encoding="utf-8").strip()


def _resolve_topic(config: dict[str, Any], topic: str | None) -> str:
    candidates = [
        topic,
        str(config.get("research_question", "")).strip(),
        str(config.get("title", "")).strip(),
        str(config.get("name", "")).strip(),
    ]
    for candidate in candidates:
        if candidate:
            return str(candidate).strip()
    raise OutlineGeneratorError("Provide --topic or set project title/research_question.")


def _llm_settings(config: dict[str, Any]) -> LLMSettings:
    llm = config.get("llm", {}) if isinstance(config, dict) else {}
    return LLMSettings(
        provider=str(llm.get("provider", "openai_compatible")),
        base_url=str(llm.get("base_url", "http://localhost:11434/v1")),
        model=str(llm.get("model", "configure-me")),
        api_key_env=str(llm.get("api_key_env", "OPENAI_API_KEY")),
        temperature=float(llm.get("temperature", 0.2)),
        max_tokens=int(llm.get("max_tokens", 1800)),
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
        raise OutlineGeneratorError(f"Project is missing required structure: {status.root}")
    return ProjectPaths(project_root(projects_root, project_name))


def _run_id() -> str:
    return "outline_" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", value.strip().lower()).strip("_")
    return slug or "outline"
