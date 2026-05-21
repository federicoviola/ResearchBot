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
from academic_paper_cli.bibliography_enrichment import (
    BibliographyEnrichmentError,
    accept_bibliography_candidate,
    diagnose_missing_identifiers,
    enrich_all_bibliography_records,
    enrich_bibliography_record,
    search_bibliography_candidates,
)
from academic_paper_cli.dataset_manager import (
    DatasetManagerError,
    add_pdf,
    add_pdfs,
    list_documents,
)
from academic_paper_cli.index_builder import (
    IndexBuilderError,
    build_index,
    get_index_status,
)
from academic_paper_cli.pdf_processor import PdfProcessorError, ingest_project
from academic_paper_cli.project_manager import (
    ProjectManagerError,
    create_project,
    get_project_status,
)
from academic_paper_cli.retrieval_engine import RetrievalEngineError, retrieve_chunks

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

    biblio_enrich = subparsers.add_parser(
        "biblio-enrich",
        help="Enrich bibliographic metadata from DOI or ISBN lookup.",
    )
    biblio_enrich.add_argument("--project", required=True, help="Project folder name.")
    biblio_enrich.add_argument("--doc-id", help="Document ID.")
    biblio_enrich.add_argument(
        "--all",
        action="store_true",
        help="Enrich all records that already contain DOI or ISBN metadata.",
    )
    biblio_enrich.add_argument("--doi", help="DOI to look up through Crossref/DataCite.")
    biblio_enrich.add_argument("--isbn", help="ISBN to look up through Open Library.")
    biblio_enrich.add_argument(
        "--auto-verify",
        action="store_true",
        help="Mark enriched metadata as verified after lookup.",
    )
    biblio_enrich.add_argument(
        "--force",
        action="store_true",
        help="Allow overwriting an already verified bibliographic record.",
    )
    biblio_enrich.add_argument(
        "--projects-root",
        default="projects",
        help="Root folder containing all paper projects.",
    )

    biblio_missing = subparsers.add_parser(
        "biblio-missing-identifiers",
        help="Show records that still lack DOI/ISBN identifiers.",
    )
    biblio_missing.add_argument("--project", required=True, help="Project folder name.")
    biblio_missing.add_argument(
        "--projects-root",
        default="projects",
        help="Root folder containing all paper projects.",
    )

    biblio_search = subparsers.add_parser(
        "biblio-search",
        help="Search external services for candidate metadata without applying it.",
    )
    biblio_search.add_argument("--project", required=True, help="Project folder name.")
    biblio_search.add_argument("--doc-id", required=True, help="Document ID.")
    biblio_search.add_argument("--title", help="Search title override.")
    biblio_search.add_argument("--author", help="Search author override.")
    biblio_search.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum number of candidates to return.",
    )
    biblio_search.add_argument(
        "--projects-root",
        default="projects",
        help="Root folder containing all paper projects.",
    )

    biblio_accept = subparsers.add_parser(
        "biblio-accept-candidate",
        help="Apply one stored bibliographic candidate to a record.",
    )
    biblio_accept.add_argument("--project", required=True, help="Project folder name.")
    biblio_accept.add_argument("--doc-id", required=True, help="Document ID.")
    biblio_accept.add_argument(
        "--candidate",
        type=int,
        required=True,
        help="1-based candidate number from biblio-search output.",
    )
    biblio_accept.add_argument(
        "--verified",
        action="store_true",
        help="Mark the accepted metadata as verified.",
    )
    biblio_accept.add_argument(
        "--force",
        action="store_true",
        help="Allow overwriting an already verified bibliographic record.",
    )
    biblio_accept.add_argument(
        "--projects-root",
        default="projects",
        help="Root folder containing all paper projects.",
    )

    build_index_parser = subparsers.add_parser(
        "build-index",
        help="Chunk extracted texts and build the local retrieval index.",
    )
    build_index_parser.add_argument("--project", required=True, help="Project folder name.")
    build_index_parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild an existing index.",
    )
    build_index_parser.add_argument(
        "--chunk-size",
        type=int,
        help="Chunk size in words. Defaults to config/project.yaml retrieval.chunk_size.",
    )
    build_index_parser.add_argument(
        "--chunk-overlap",
        type=int,
        help="Chunk overlap in words. Defaults to config/project.yaml retrieval.chunk_overlap.",
    )
    build_index_parser.add_argument(
        "--embedding-backend",
        default="hashing",
        help="Embedding backend. Currently only 'hashing' is implemented.",
    )
    build_index_parser.add_argument(
        "--embedding-dimensions",
        type=int,
        default=256,
        help="Embedding vector dimensions for the hashing backend.",
    )
    build_index_parser.add_argument(
        "--projects-root",
        default="projects",
        help="Root folder containing all paper projects.",
    )

    index_status = subparsers.add_parser(
        "index-status",
        help="Show local retrieval index status.",
    )
    index_status.add_argument("--project", required=True, help="Project folder name.")
    index_status.add_argument(
        "--projects-root",
        default="projects",
        help="Root folder containing all paper projects.",
    )

    retrieve = subparsers.add_parser(
        "retrieve",
        help="Retrieve relevant chunks from the local project index.",
    )
    retrieve.add_argument("--project", required=True, help="Project folder name.")
    retrieve.add_argument("query", help="Search query.")
    retrieve.add_argument(
        "--top-k",
        type=int,
        help="Number of chunks to return. Defaults to config/project.yaml retrieval.top_k.",
    )
    retrieve.add_argument(
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

        if args.command == "biblio-enrich":
            if args.all:
                result = enrich_all_bibliography_records(
                    project_name=args.project,
                    projects_root=Path(args.projects_root),
                    auto_verify=args.auto_verify,
                    force=args.force,
                )
                console.print(
                    "[green]Bulk enrichment complete:[/green] "
                    f"{result.enriched_count} enriched, "
                    f"{result.skipped_count} skipped, "
                    f"{result.failed_count} failed"
                )
                _render_enrichment_results(result.results, title="Bibliography Enrichment")
                if result.skipped:
                    console.print("[yellow]Skipped records without DOI/ISBN:[/yellow]")
                    for document_id in result.skipped:
                        console.print(f"  - {document_id}")
                if result.failed:
                    console.print("[red]Failed records:[/red]")
                    for document_id, message in result.failed.items():
                        console.print(f"  - {document_id}: {message}")
                return 0 if not result.failed else 2

            if not args.doc_id:
                raise BibliographyEnrichmentError("--doc-id is required unless --all is used.")
            result = enrich_bibliography_record(
                project_name=args.project,
                document_id=args.doc_id,
                projects_root=Path(args.projects_root),
                doi=args.doi,
                isbn=args.isbn,
                auto_verify=args.auto_verify,
                force=args.force,
            )
            console.print(
                f"[green]Enriched bibliography:[/green] {result.record.document_id} "
                f"from {result.source}"
            )
            _render_bibliography([result.record], title=f"Bibliographic Record: {args.doc_id}")
            return 0

        if args.command == "biblio-missing-identifiers":
            diagnostics = diagnose_missing_identifiers(
                project_name=args.project,
                projects_root=Path(args.projects_root),
            )
            _render_identifier_diagnostics(
                diagnostics,
                title=f"Missing Identifiers: {args.project}",
            )
            return 0

        if args.command == "biblio-search":
            candidates = search_bibliography_candidates(
                project_name=args.project,
                document_id=args.doc_id,
                projects_root=Path(args.projects_root),
                title=args.title,
                author=args.author,
                limit=args.limit,
            )
            _render_candidates(candidates, title=f"Candidates: {args.doc_id}")
            return 0

        if args.command == "biblio-accept-candidate":
            result = accept_bibliography_candidate(
                project_name=args.project,
                document_id=args.doc_id,
                candidate_number=args.candidate,
                projects_root=Path(args.projects_root),
                verified=args.verified,
                force=args.force,
            )
            console.print(
                f"[green]Accepted candidate:[/green] {args.doc_id} "
                f"#{args.candidate} from {result.source}"
            )
            _render_bibliography([result.record], title=f"Bibliographic Record: {args.doc_id}")
            return 0

        if args.command == "build-index":
            result = build_index(
                project_name=args.project,
                projects_root=Path(args.projects_root),
                force=args.force,
                chunk_size=args.chunk_size,
                chunk_overlap=args.chunk_overlap,
                embedding_backend=args.embedding_backend,
                embedding_dimensions=args.embedding_dimensions,
            )
            console.print(
                "[green]Built index:[/green] "
                f"{result.document_count} documents, {result.chunk_count} chunks"
            )
            _render_index_build_result(result)
            return 0

        if args.command == "index-status":
            status = get_index_status(
                project_name=args.project,
                projects_root=Path(args.projects_root),
            )
            _render_index_status(status)
            return 0 if status.status == "built" else 2

        if args.command == "retrieve":
            results = retrieve_chunks(
                project_name=args.project,
                query=args.query,
                projects_root=Path(args.projects_root),
                top_k=args.top_k,
            )
            _render_retrieval_results(results, title=f"Retrieval: {args.project}")
            return 0 if results else 2

    except (
        ProjectManagerError,
        DatasetManagerError,
        PdfProcessorError,
        BibliographyManagerError,
        BibliographyEnrichmentError,
        IndexBuilderError,
        RetrievalEngineError,
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


def _render_enrichment_results(results, title: str) -> None:
    if not results:
        return

    table = Table(title=title)
    table.add_column("Document ID", style="bold")
    table.add_column("Source")
    table.add_column("Status")
    table.add_column("Year")
    table.add_column("Citation Key")
    table.add_column("Title")

    for result in results:
        table.add_row(
            result.record.document_id,
            result.source,
            result.record.metadata_status,
            result.record.year,
            result.record.citation_key,
            result.record.title,
        )

    console.print(table)


def _render_index_build_result(result) -> None:
    table = Table(title=f"Index Build: {result.project_name}")
    table.add_column("Field", style="bold")
    table.add_column("Value")

    table.add_row("Documents", str(result.document_count))
    table.add_row("Chunks", str(result.chunk_count))
    table.add_row("Embedding backend", result.embedding_backend)
    table.add_row("Embedding dimensions", str(result.embedding_dimensions))
    table.add_row("Chunks path", result.chunks_path)
    table.add_row("Embeddings path", result.embeddings_path)
    table.add_row("State path", result.status_path)
    table.add_row("Built at", result.built_at)

    console.print(table)


def _render_index_status(status) -> None:
    state_color = "green" if status.status == "built" else "yellow"
    table = Table(title=f"Index Status: {status.project_name}")
    table.add_column("Field", style="bold")
    table.add_column("Value")

    table.add_row("Status", f"[{state_color}]{status.status}[/{state_color}]")
    table.add_row("Documents", str(status.document_count))
    table.add_row("Chunks", str(status.chunk_count))
    table.add_row("Embedding backend", status.embedding_backend)
    table.add_row("Embedding dimensions", str(status.embedding_dimensions))
    table.add_row("Chunks path", status.chunks_path)
    table.add_row("Embeddings path", status.embeddings_path)
    table.add_row("Built at", status.built_at)
    if status.message:
        table.add_row("Message", status.message)

    console.print(table)


def _render_retrieval_results(results, title: str) -> None:
    if not results:
        console.print("[yellow]No relevant chunks found.[/yellow]")
        return

    table = Table(title=title)
    table.add_column("#", style="bold")
    table.add_column("Score")
    table.add_column("Chunk")
    table.add_column("Source")
    table.add_column("Excerpt")

    for result in results:
        chunk = result.chunk
        authors = "; ".join(chunk.authors)
        source = " | ".join(
            value for value in [chunk.title, authors, chunk.year] if value
        )
        table.add_row(
            str(result.rank),
            f"{result.score:.3f}",
            chunk.chunk_id,
            source or chunk.document_id,
            _excerpt(chunk.text),
        )

    console.print(table)


def _excerpt(text: str, limit: int = 280) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def _render_identifier_diagnostics(diagnostics, title: str) -> None:
    if not diagnostics:
        console.print("[green]All bibliographic records have DOI or ISBN identifiers.[/green]")
        return

    table = Table(title=title)
    table.add_column("Document ID", style="bold")
    table.add_column("File")
    table.add_column("Year")
    table.add_column("Title")
    table.add_column("Suggestion")

    for diagnostic in diagnostics:
        table.add_row(
            diagnostic.document_id,
            diagnostic.original_filename,
            diagnostic.year,
            diagnostic.title,
            diagnostic.suggestion,
        )

    console.print(table)


def _render_candidates(candidates, title: str) -> None:
    if not candidates:
        console.print("[yellow]No candidates found.[/yellow]")
        return

    table = Table(title=title)
    table.add_column("#", style="bold")
    table.add_column("Source")
    table.add_column("Year")
    table.add_column("Authors")
    table.add_column("Title")
    table.add_column("DOI")
    table.add_column("ISBN")

    for index, candidate in enumerate(candidates, start=1):
        authors = "; ".join(
            f"{author.family}, {author.given}".strip().strip(",")
            for author in candidate.authors
        )
        table.add_row(
            str(index),
            candidate.source,
            candidate.year,
            authors,
            candidate.title,
            candidate.doi,
            candidate.isbn,
        )

    console.print(table)
