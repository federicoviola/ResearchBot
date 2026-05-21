"""Module 1: project folder creation, validation, and status."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from academic_paper_cli.models import ProjectConfig, ProjectPaths, ProjectStatus


PROJECT_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")


class ProjectManagerError(ValueError):
    """Raised for project manager validation errors."""


def validate_project_name(name: str) -> str:
    """Validate and return a safe folder name."""

    normalized = name.strip()
    if not normalized:
        raise ProjectManagerError("Project name cannot be empty.")
    if not PROJECT_NAME_PATTERN.fullmatch(normalized):
        raise ProjectManagerError(
            "Project name may only contain letters, numbers, underscores, and "
            "hyphens, and must start with a letter or number."
        )
    return normalized


def project_root(projects_root: Path, name: str) -> Path:
    """Resolve a project name under the configured projects root."""

    safe_name = validate_project_name(name)
    return projects_root.expanduser().resolve() / safe_name


def create_project(name: str, projects_root: Path = Path("projects")) -> ProjectStatus:
    """Create the complete Module 1 project folder contract."""

    root = project_root(projects_root, name)
    paths = ProjectPaths(root)

    if root.exists() and any(root.iterdir()):
        raise ProjectManagerError(f"Project already exists and is not empty: {root}")

    for directory in paths.required_directories:
        directory.mkdir(parents=True, exist_ok=True)

    project_config = ProjectConfig(
        name=name,
        title=name.replace("_", " ").replace("-", " ").title(),
    )

    _write_yaml_if_missing(paths.config_dir / "project.yaml", project_config.to_dict())
    _write_text_if_missing(paths.config_dir / "system_prompt.md", _default_system_prompt())
    _write_text_if_missing(paths.config_dir / "writing_style.md", _default_writing_style())
    _write_yaml_if_missing(paths.config_dir / "citation_style.yaml", _default_citation_style())
    _write_text_if_missing(paths.skills_dir / "outline_design.md", _default_outline_skill())

    created_at = _utc_now_iso()
    _write_json_if_missing(
        paths.state_dir / "ingestion_state.json",
        {
            "version": 1,
            "created_at": created_at,
            "updated_at": created_at,
            "documents": {},
        },
    )
    _write_json_if_missing(
        paths.state_dir / "index_state.json",
        {
            "version": 1,
            "created_at": created_at,
            "updated_at": created_at,
            "status": "not_built",
            "index_backend": None,
            "chunk_count": 0,
        },
    )
    _write_json_if_missing(
        paths.state_dir / "run_history.json",
        {
            "version": 1,
            "created_at": created_at,
            "runs": [],
        },
    )

    return get_project_status(name, projects_root)


def get_project_status(name: str, projects_root: Path = Path("projects")) -> ProjectStatus:
    """Validate the project structure and return a status object."""

    root = project_root(projects_root, name)
    paths = ProjectPaths(root)
    exists = root.exists()

    missing_directories = [
        directory for directory in paths.required_directories if not directory.is_dir()
    ]
    missing_files = [file_path for file_path in paths.required_files if not file_path.is_file()]

    pdf_count = _count_files(paths.dataset_dir / "pdf", "*.pdf")
    text_count = _count_files(paths.dataset_dir / "txt", "*.txt")
    metadata_count = _count_files(paths.dataset_dir / "metadata", "*.json")
    skill_count = _count_files(paths.skills_dir, "*.md")

    return ProjectStatus(
        project_name=validate_project_name(name),
        root=root,
        exists=exists,
        valid=exists and not missing_directories and not missing_files,
        missing_directories=missing_directories,
        missing_files=missing_files,
        pdf_count=pdf_count,
        text_count=text_count,
        metadata_count=metadata_count,
        skill_count=skill_count,
    )


def _write_text_if_missing(path: Path, content: str) -> None:
    if not path.exists():
        path.write_text(content, encoding="utf-8")


def _write_json_if_missing(path: Path, payload: dict[str, Any]) -> None:
    if not path.exists():
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_yaml_if_missing(path: Path, payload: dict[str, Any]) -> None:
    if not path.exists():
        path.write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=False),
            encoding="utf-8",
        )


def _count_files(directory: Path, pattern: str) -> int:
    if not directory.is_dir():
        return 0
    return sum(1 for item in directory.glob(pattern) if item.is_file())


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _default_system_prompt() -> str:
    return """# System Prompt

You are an academic assistant working over a closed bibliographic dataset.

Core rule: only use retrieved dataset context. Do not introduce external claims,
invent citations, fabricate bibliography entries, or imply source support that is
not present in the retrieved corpus. If the dataset is insufficient, say so
explicitly and identify what evidence is missing.
"""


def _default_writing_style() -> str:
    return """# Writing Style

- Write in a precise academic tone.
- Prefer clear claims tied to explicit source evidence.
- Separate interpretation from direct dataset support.
- Avoid rhetorical overstatement.
"""


def _default_citation_style() -> dict[str, Any]:
    return {
        "style": "author_year",
        "require_page_when_available": True,
        "bibliography_policy": "only_dataset_metadata",
        "missing_metadata_policy": "cite_document_id_and_report_missing_fields",
    }


def _default_outline_skill() -> str:
    return """# Outline Design Skill

Design an academic paper outline grounded only in retrieved dataset context.

Every major section must include:
- A concise section purpose.
- The dataset documents or chunks that support the section.
- A note when available evidence is weak, partial, or absent.
"""
