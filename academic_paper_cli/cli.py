"""Command line interface for the academic paper CLI."""

from __future__ import annotations

import argparse
from pathlib import Path

from rich.console import Console
from rich.table import Table

from academic_paper_cli.dataset_manager import (
    DatasetManagerError,
    add_pdf,
    list_documents,
)
from academic_paper_cli.project_manager import (
    ProjectManagerError,
    create_project,
    get_project_status,
)

console = Console()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python main.py",
        description="CLI-first AI-assisted academic paper production system.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_project = subparsers.add_parser(
        "init-project",
        help="Create a paper project folder with default configuration.",
    )
    init_project.add_argument("--name", required=True, help="Project folder name.")
    init_project.add_argument(
        "--projects-root",
        default="projects",
        help="Root folder containing all paper projects.",
    )

    status = subparsers.add_parser(
        "status",
        help="Validate project structure and show Module 1 status.",
    )
    status.add_argument("--project", required=True, help="Project folder name.")
    status.add_argument(
        "--projects-root",
        default="projects",
        help="Root folder containing all paper projects.",
    )

    add_pdf_parser = subparsers.add_parser(
        "add-pdf",
        help="Add an academic PDF to a project dataset.",
    )
    add_pdf_parser.add_argument("--project", required=True, help="Project folder name.")
    add_pdf_parser.add_argument("--file", required=True, help="Path to the PDF file.")
    add_pdf_parser.add_argument(
        "--projects-root",
        default="projects",
        help="Root folder containing all paper projects.",
    )

    list_docs = subparsers.add_parser(
        "list-docs",
        help="List PDFs registered in a project dataset.",
    )
    list_docs.add_argument("--project", required=True, help="Project folder name.")
    list_docs.add_argument(
        "--projects-root",
        default="projects",
        help="Root folder containing all paper projects.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "init-project":
            status = create_project(
                name=args.name,
                projects_root=Path(args.projects_root),
            )
            console.print(f"[green]Created project:[/green] {status.project_name}")
            _render_status(status)
            return 0

        if args.command == "status":
            status = get_project_status(
                name=args.project,
                projects_root=Path(args.projects_root),
            )
            _render_status(status)
            return 0 if status.valid else 2

        if args.command == "add-pdf":
            result = add_pdf(
                project_name=args.project,
                source_file=Path(args.file),
                projects_root=Path(args.projects_root),
            )
            if result.added:
                console.print(
                    f"[green]Added PDF:[/green] {result.record.document_id} "
                    f"({result.record.original_filename})"
                )
            else:
                console.print(
                    f"[yellow]Duplicate PDF:[/yellow] already registered as "
                    f"{result.duplicate_of}"
                )
            _render_documents([result.record], title="Document")
            return 0

        if args.command == "list-docs":
            documents = list_documents(
                project_name=args.project,
                projects_root=Path(args.projects_root),
            )
            _render_documents(documents, title=f"Documents: {args.project}")
            return 0

    except (ProjectManagerError, DatasetManagerError) as error:
        console.print(f"[red]Error:[/red] {error}")
        return 1

    parser.error(f"Unknown command: {args.command}")
    return 1


def _render_status(status) -> None:
    state = "valid" if status.valid else "invalid"
    state_color = "green" if status.valid else "red"

    table = Table(title=f"Project Status: {status.project_name}")
    table.add_column("Field", style="bold")
    table.add_column("Value")

    table.add_row("Root", str(status.root))
    table.add_row("Exists", str(status.exists))
    table.add_row("Status", f"[{state_color}]{state}[/{state_color}]")
    table.add_row("PDF files", str(status.pdf_count))
    table.add_row("Extracted text files", str(status.text_count))
    table.add_row("Metadata files", str(status.metadata_count))
    table.add_row("Skill files", str(status.skill_count))
    table.add_row("Missing items", str(status.missing_count))

    console.print(table)

    if status.missing_directories:
        console.print("[yellow]Missing directories:[/yellow]")
        for path in status.missing_directories:
            console.print(f"  - {path}")

    if status.missing_files:
        console.print("[yellow]Missing files:[/yellow]")
        for path in status.missing_files:
            console.print(f"  - {path}")


def _render_documents(documents, title: str) -> None:
    if not documents:
        console.print("[yellow]No registered documents.[/yellow]")
        return

    table = Table(title=title)
    table.add_column("Document ID", style="bold")
    table.add_column("Original File")
    table.add_column("Status")
    table.add_column("SHA-256")
    table.add_column("Stored Path")

    for document in documents:
        table.add_row(
            document.document_id,
            document.original_filename,
            document.status,
            document.sha256[:12],
            document.stored_path,
        )

    console.print(table)
