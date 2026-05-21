"""Typed project models for the academic paper CLI.

Later modules can replace or extend these dataclasses with Pydantic models
without changing the folder contract created by the project manager.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LLMProviderConfig:
    """Configures an OpenAI-compatible or local LLM provider."""

    provider: str = "openai_compatible"
    base_url: str = "http://localhost:11434/v1"
    model: str = "configure-me"
    api_key_env: str = "OPENAI_API_KEY"
    temperature: float = 0.2
    max_tokens: int = 1800

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "base_url": self.base_url,
            "model": self.model,
            "api_key_env": self.api_key_env,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }


@dataclass(frozen=True)
class RetrievalConfig:
    """Default retrieval controls for future RAG modules."""

    top_k: int = 8
    chunk_size: int = 900
    chunk_overlap: int = 150
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    def to_dict(self) -> dict[str, Any]:
        return {
            "top_k": self.top_k,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "embedding_model": self.embedding_model,
        }


@dataclass(frozen=True)
class GroundingPolicy:
    """Rules that preserve the closed-corpus authority principle."""

    require_sources: bool = True
    allow_external_knowledge: bool = False
    unsupported_answer: str = (
        "The dataset does not contain enough information to answer this "
        "without unsupported claims."
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "require_sources": self.require_sources,
            "allow_external_knowledge": self.allow_external_knowledge,
            "unsupported_answer": self.unsupported_answer,
        }


@dataclass(frozen=True)
class ProjectConfig:
    """Paper-level configuration written to config/project.yaml."""

    name: str
    title: str
    description: str = ""
    research_question: str = ""
    language: str = "en"
    llm: LLMProviderConfig = field(default_factory=LLMProviderConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    grounding: GroundingPolicy = field(default_factory=GroundingPolicy)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "research_question": self.research_question,
            "language": self.language,
            "llm": self.llm.to_dict(),
            "retrieval": self.retrieval.to_dict(),
            "grounding": self.grounding.to_dict(),
        }


@dataclass(frozen=True)
class ProjectPaths:
    """Canonical paths for a paper project."""

    root: Path

    @property
    def config_dir(self) -> Path:
        return self.root / "config"

    @property
    def skills_dir(self) -> Path:
        return self.config_dir / "skills"

    @property
    def dataset_dir(self) -> Path:
        return self.root / "dataset"

    @property
    def outputs_dir(self) -> Path:
        return self.root / "outputs"

    @property
    def state_dir(self) -> Path:
        return self.root / "state"

    @property
    def required_directories(self) -> list[Path]:
        return [
            self.root,
            self.config_dir,
            self.skills_dir,
            self.dataset_dir / "pdf",
            self.dataset_dir / "txt",
            self.dataset_dir / "metadata",
            self.dataset_dir / "index",
            self.outputs_dir / "outlines",
            self.outputs_dir / "notes",
            self.outputs_dir / "logs",
            self.outputs_dir / "reports",
            self.state_dir,
        ]

    @property
    def required_files(self) -> list[Path]:
        return [
            self.config_dir / "project.yaml",
            self.config_dir / "system_prompt.md",
            self.config_dir / "writing_style.md",
            self.config_dir / "citation_style.yaml",
            self.skills_dir / "outline_design.md",
            self.state_dir / "ingestion_state.json",
            self.state_dir / "index_state.json",
            self.state_dir / "run_history.json",
        ]


@dataclass(frozen=True)
class ProjectStatus:
    """Validation result for a project folder."""

    project_name: str
    root: Path
    exists: bool
    valid: bool
    missing_directories: list[Path]
    missing_files: list[Path]
    pdf_count: int
    text_count: int
    metadata_count: int
    skill_count: int

    @property
    def missing_count(self) -> int:
        return len(self.missing_directories) + len(self.missing_files)


@dataclass(frozen=True)
class DocumentRecord:
    """Registered source PDF in a project dataset."""

    document_id: str
    original_filename: str
    source_path: str
    stored_path: str
    sha256: str
    added_at: str
    status: str = "pending_ingestion"

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "original_filename": self.original_filename,
            "source_path": self.source_path,
            "stored_path": self.stored_path,
            "sha256": self.sha256,
            "added_at": self.added_at,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DocumentRecord":
        return cls(
            document_id=str(payload["document_id"]),
            original_filename=str(payload["original_filename"]),
            source_path=str(payload["source_path"]),
            stored_path=str(payload["stored_path"]),
            sha256=str(payload["sha256"]),
            added_at=str(payload["added_at"]),
            status=str(payload.get("status", "pending_ingestion")),
        )


@dataclass(frozen=True)
class AddPdfResult:
    """Result of registering a PDF."""

    record: DocumentRecord
    added: bool
    duplicate_of: str | None = None
    input_path: str | None = None


@dataclass(frozen=True)
class BulkAddPdfResult:
    """Result of registering PDFs from multiple files or folders."""

    results: list[AddPdfResult]
    skipped_paths: list[str] = field(default_factory=list)

    @property
    def added_count(self) -> int:
        return sum(1 for result in self.results if result.added)

    @property
    def duplicate_count(self) -> int:
        return sum(1 for result in self.results if not result.added)

    @property
    def total_pdf_count(self) -> int:
        return len(self.results)


@dataclass(frozen=True)
class IngestionResult:
    """Result of extracting text and metadata from a registered PDF."""

    document_id: str
    original_filename: str
    status: str
    text_path: str | None
    metadata_path: str | None
    page_count: int = 0
    character_count: int = 0
    word_count: int = 0
    error: str | None = None
