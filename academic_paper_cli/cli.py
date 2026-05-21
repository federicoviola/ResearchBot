"""Command line interface for the academic paper CLI."""

from __future__ import annotations

import argparse
from pathlib import Path

from rich.console import Console
from rich.table import Table

from academic_paper_cli.bibliography_manager import (
    BibliographyManagerError,
    export_bibliography,
    init_bibliography,
    list_bibliography,
    set_bibliography_record,
    show_bibliography_record,
    validate_bibliography,
)
from academic_paper_cli.dataset_manager import (
    DatasetManagerError,
    add_pdf,
    add_pdfs,
    list_documents,
)
from academic_paper_cli.pdf_processor import PdfProcessorError, ingest_project
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
        help="Validate project structure and show project status.",
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

    add_pdfs_parser = subparsers.add_parser(
        "add-pdfs",
        help="Bulk add PDFs from files or folders to a project dataset.",
    )
    add_pdfs_parser.add_argument("--project", required=True, help="Project folder name.")
    add_pdfs_parser.add_argument(
        "--path",
        action="append",
        required=True,
        help="PDF file or folder path. Can be provided multiple times.",
    )
    add_pdfs_parser.add_argument(
        "--recursive",
        action="store_true",
        help="Search folders recursively for PDF files.",
    )
    add_pdfs_parser.add_argument(
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

    ingest = subparsers.add_parser(
        "ingest",
        help="Extract text and metadata from registered PDFs.",
    )
    ingest.add_argument("--project", required=True, help="Project folder name.")
    ingest.add_argument(
        "--projects-root",
        default="projects",
        help="Root folder containing all paper projects.",
    )
    ingest.add_argument(
        "--force",
        action="store_true",
        help="Re-extract PDFs that are already marked as ingested.",
    )

    biblio_init = subparsers.add_parser(
        "biblio-init",
        help="Create editable bibliographic metadata templates for registered PDFs.",
    )
    biblio_init.add_argument("--project", required=True, help="Project folder name.")
    biblio_init.add_argument(
        "--projects-root",
        default="projects",
        help="Root folder containing all paper projects.",
    )

    biblio_list = subparsers.add_parser(
        "biblio-list",
        help="List curated bibliographic records.",
    )
    biblio_list.add_argument("--project", required=True, help="Project folder name.")
    biblio_list.add_argument(
        "--projects-root",
        default="projects",
        help="Root folder containing all paper projects.",
    )

    biblio_show = subparsers.add_parser(
        "biblio-show",
        help="Show one bibliographic record.",
    )
    biblio_show.add_argument("--project", required=True, help="Project folder name.")
    biblio_show.add_argument("--doc-id", required=True, help="Document ID.")
    biblio_show.add_argument(
        "--projects-root",
        default="projects",
        help="Root folder containing all paper projects.",
    )

    biblio_set = subparsers.add_parser(
        "biblio-set",
        help="Set bibliographic metadata for one document.",
    )
    biblio_set.add_argument("--project", required=True, help="Project folder name.")
    biblio_set.add_argument("--doc-id", required=True, help="Document ID.")
    biblio_set.add_argument("--type", dest="item_type", help="Item type.")
    biblio_set.add_argument("--title", help="Bibliographic title.")
    biblio_set.add_argument(
        "--author",
        action="append",
        help='Author as "Family, Given". Can be provided multiple times.',
    )
    biblio_set.add_argument("--year", help="Publication year.")
    biblio_set.add_argument("--publisher", help="Publisher or institution.")
    biblio_set.add_argument("--place", help="Publication place.")
    biblio_set.add_argument("--journal", help="Journal or container title.")
    biblio_set.add_argument("--volume", help="Volume.")
    biblio_set.add_argument("--issue", help="Issue.")
    biblio_set.add_argument("--pages", help="Page range.")
    biblio_set.add_argument("--doi", help="DOI.")
    biblio_set.add_argument("--isbn", help="ISBN.")
    biblio_set.add_argument("--url", help="URL.")
    biblio_set.add_argument("--language", help="Language code.")
    biblio_set.add_argument("--citation-key", help="Stable citation key.")
    biblio_set.add_argument("--notes", help="Curator notes.")
    biblio_set.add_argument(
        "--status",
        choices=["needs_review", "verified"],
        help="Metadata review status.",
    )
    biblio_set.add_argument(
        "--verified",
        action="store_true",
        help="Shortcut for --status verified.",
    )
    biblio_set.add_argument(
        "--projects-root",
        default="projects",
        help="Root folder containing all paper projects.",
    )

    biblio_validate = subparsers.add_parser(
        "biblio-validate",
        help="Validate bibliographic metadata completeness.",
    )
    biblio_validate.add_argument("--project", required=True, help="Project folder name.")
    biblio_validate.add_argument(
        "--allow-unverified",
        action="store_true",
        help="Do not require metadata_status=verified.",
    )
    biblio_validate.add_argument(
        "--projects-root",
        default="projects",
        help="Root folder containing all paper projects.",
    )

    biblio_export = subparsers.add_parser(
        "biblio-export",
        help="Export verified bibliographic records.",
    )
    biblio_export.add_argument("--project", required=True, help="Project folder name.")
    biblio_export.add_argument(
        "--format",
        choices=["bibtex", "csl-json"],
        default="bibtex",
        help="Export format.",
    )
    biblio_export.add_argument(
        "--include-unverified",
        action="store_true",
        help="Include records that are not marked verified.",
    )
    biblio_export.add_argument(
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

        if args.command == "add-pdfs":
            result = add_pdfs(
                project_name=args.project,
                paths=[Path(path) for path in args.path],
                projects_root=Path(args.projects_root),
                recursive=args.recursive,
            )
            console.print(
                "[green]Bulk add complete:[/green] "
                f"{result.added_count} added, "
                f"{result.duplicate_count} duplicates, "
                f"{len(result.skipped_paths)} skipped paths"
            )
            _render_add_pdf_results(result.results, title="Bulk Documents")
            if result.skipped_paths:
                console.print("[yellow]Skipped paths:[/yellow]")
                for skipped_path in result.skipped_paths:
                    console.print(f"  - {skipped_path}")
            return 0

        if args.command == "list-docs":
            documents = list_documents(
                project_name=args.project,
                projects_root=Path(args.projects_root),
            )
            _render_documents(documents, title=f"Documents: {args.project}")
            return 0

        if args.command == "ingest":
            results = ingest_project(
                project_name=args.project,
                projects_root=Path(args.projects_root),
                force=args.force,
            )
            _render_ingestion_results(results, title=f"Ingestion: {args.project}")
            return 0 if all(result.status != "ingestion_failed" for result in results) else 2

        if args.command == "biblio-init":
            records = init_bibliography(
                project_name=args.project,
                projects_root=Path(args.projects_root),
            )
            _render_bibliography(records, title=f"Bibliography: {args.project}")
            return 0

        if args.command == "biblio-list":
            records = list_bibliography(
                project_name=args.project,
                projects_root=Path(args.projects_root),
            )
            _render_bibliography(records, title=f"Bibliography: {args.project}")
            return 0

        if args.command == "biblio-show":
            record = show_bibliography_record(
                project_name=args.project,
                document_id=args.doc_id,
                projects_root=Path(args.projects_root),
            )
            _render_bibliography([record], title=f"Bibliographic Record: {args.doc_id}")
            return 0

        if args.command == "biblio-set":
            authors = None
            if args.author is not None:
                from academic_paper_cli.models import BibliographicAuthor

                authors = [
                    BibliographicAuthor.from_string(author)
                    for author in args.author
                ]
            record = set_bibliography_record(
                project_name=args.project,
                document_id=args.doc_id,
                projects_root=Path(args.projects_root),
                item_type=args.item_type,
                title=args.title,
                authors=authors,
                year=args.year,
                publisher=args.publisher,
                place=args.place,
                journal=args.journal,
                volume=args.volume,
                issue=args.issue,
                pages=args.pages,
                doi=args.doi,
                isbn=args.isbn,
                url=args.url,
                language=args.language,
                citation_key=args.citation_key,
                notes=args.notes,
                metadata_status=args.status,
                verified=args.verified,
            )
            _render_bibliography([record], title=f"Bibliographic Record: {args.doc_id}")
            return 0

        if args.command == "biblio-validate":
            results = validate_bibliography(
                project_name=args.project,
                projects_root=Path(args.projects_root),
                require_verified=not args.allow_unverified,
            )
            _render_bibliography_validation(results, title=f"Bibliography Validation: {args.project}")
            return 0 if all(result.valid for result in results) else 2

        if args.command == "biblio-export":
            output_path = export_bibliography(
                project_name=args.project,
                projects_root=Path(args.projects_root),
                export_format=args.format,
                include_unverified=args.include_unverified,
            )
            console.print(f"[green]Exported bibliography:[/green] {output_path}")
            return 0

    except (
        ProjectManagerError,
        DatasetManagerError,
        PdfProcessorError,
        BibliographyManagerError,
    ) as error:
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


def _render_add_pdf_results(results, title: str) -> None:
    if not results:
        console.print("[yellow]No PDFs registered.[/yellow]")
        return

    table = Table(title=title)
    table.add_column("Document ID", style="bold")
    table.add_column("Input File")
    table.add_column("Result")
    table.add_column("Duplicate Of")
    table.add_column("SHA-256")

    for result in results:
        input_file = (
            Path(result.input_path).name if result.input_path else result.record.original_filename
        )
        table.add_row(
            result.record.document_id,
            input_file,
            "added" if result.added else "duplicate",
            result.duplicate_of or "",
            result.record.sha256[:12],
        )

    console.print(table)


def _render_ingestion_results(results, title: str) -> None:
    if not results:
        console.print("[yellow]No registered documents to ingest.[/yellow]")
        return

    table = Table(title=title)
    table.add_column("Document ID", style="bold")
    table.add_column("Original File")
    table.add_column("Status")
    table.add_column("Pages")
    table.add_column("Words")
    table.add_column("Text Path")
    table.add_column("Error")

    for result in results:
        table.add_row(
            result.document_id,
            result.original_filename,
            result.status,
            str(result.page_count),
            str(result.word_count),
            result.text_path or "",
            result.error or "",
        )

    console.print(table)


def _render_bibliography(records, title: str) -> None:
    if not records:
        console.print("[yellow]No bibliographic records.[/yellow]")
        return

    table = Table(title=title)
    table.add_column("Document ID", style="bold")
    table.add_column("Type")
    table.add_column("Citation Key")
    table.add_column("Status")
    table.add_column("Year")
    table.add_column("Authors")
    table.add_column("Title")

    for record in records:
        authors = "; ".join(
            f"{author.family}, {author.given}".strip().strip(",")
            for author in record.authors
        )
        table.add_row(
            record.document_id,
            record.item_type,
            record.citation_key,
            record.metadata_status,
            record.year,
            authors,
            record.title,
        )

    console.print(table)


def _render_bibliography_validation(results, title: str) -> None:
    if not results:
        console.print("[yellow]No bibliographic records to validate.[/yellow]")
        return

    table = Table(title=title)
    table.add_column("Document ID", style="bold")
    table.add_column("Citation Key")
    table.add_column("Status")
    table.add_column("Valid")
    table.add_column("Missing")

    for result in results:
        table.add_row(
            result.document_id,
            result.citation_key,
            result.metadata_status,
            "yes" if result.valid else "no",
            ", ".join(result.missing_fields),
        )

    console.print(table)
