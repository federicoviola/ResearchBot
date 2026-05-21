# Academic Paper CLI

CLI-first MVP for an AI-assisted academic paper production system based on a closed bibliographic dataset.

Current implementation:

- Module 1: Project Manager
- Module 2: Dataset Manager
- Module 3: PDF Processor
- Module 3.5: Bibliographic Metadata Manager
- Module 3.6: Bibliographic Metadata Enrichment

## Requirements

- Python 3.11 or newer
- `pip`

This workspace currently uses `python3`. If your machine maps `python` to Python 3, you can use `python` instead.

## Create a Python Environment

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
```

When the environment is active, your shell prompt usually shows `(.venv)`.

To leave the environment:

```bash
deactivate
```

To reactivate it later:

```bash
source .venv/bin/activate
```

## Run Tests

```bash
python3 -m unittest
```

## Module 1 Usage

Create a paper project:

```bash
python3 main.py init-project --name autonomy_blockchain_paper
```

Check project status:

```bash
python3 main.py status --project autonomy_blockchain_paper
```

The command creates:

```text
projects/autonomy_blockchain_paper/
├── config/
├── dataset/
├── outputs/
└── state/
```

## Module 2 Usage

Add a PDF to a project dataset:

```bash
python3 main.py add-pdf --project autonomy_blockchain_paper --file ./sources/castoriadis.pdf
```

Bulk add PDFs from a folder:

```bash
python3 main.py add-pdfs --project autonomy_blockchain_paper --path ./sources
```

Bulk add PDFs recursively from a folder:

```bash
python3 main.py add-pdfs --project autonomy_blockchain_paper --path ./sources --recursive
```

You can also pass `--path` multiple times to mix files and folders:

```bash
python3 main.py add-pdfs --project autonomy_blockchain_paper --path ./sources --path ~/Downloads/paper.pdf
```

List registered PDFs:

```bash
python3 main.py list-docs --project autonomy_blockchain_paper
```

Module 2 copies PDFs into `dataset/pdf`, assigns stable document IDs, and avoids
duplicates using SHA-256 checksums.

## Module 3 Usage

Extract text and metadata from registered PDFs:

```bash
python3 main.py ingest --project autonomy_blockchain_paper
```

Re-extract PDFs that were already ingested:

```bash
python3 main.py ingest --project autonomy_blockchain_paper --force
```

Module 3 reads PDFs from `dataset/pdf`, writes extracted text to `dataset/txt`,
writes metadata JSON to `dataset/metadata`, and updates `state/ingestion_state.json`.

## Module 3.5 Usage

Create editable bibliographic metadata templates for registered PDFs:

```bash
python3 main.py biblio-init --project autonomy_blockchain_paper
```

List bibliographic records:

```bash
python3 main.py biblio-list --project autonomy_blockchain_paper
```

Set curated metadata for a document:

```bash
python3 main.py biblio-set \
  --project autonomy_blockchain_paper \
  --doc-id doc_0001 \
  --type book \
  --title "The Imaginary Institution of Society" \
  --author "Castoriadis, Cornelius" \
  --year 1987 \
  --publisher "MIT Press" \
  --citation-key castoriadis_1987_imaginary \
  --verified
```

Validate citation readiness:

```bash
python3 main.py biblio-validate --project autonomy_blockchain_paper
```

Export verified records:

```bash
python3 main.py biblio-export --project autonomy_blockchain_paper --format bibtex
python3 main.py biblio-export --project autonomy_blockchain_paper --format csl-json
```

Bibliographic records are stored as editable YAML files in `dataset/bibliography`.
Exports are written to `outputs/reports`. By default, exports include only records
marked `verified`.

## Module 3.6 Usage

Enrich bibliographic metadata from DOI:

```bash
python3 main.py biblio-enrich \
  --project autonomy_blockchain_paper \
  --doc-id doc_0001 \
  --doi 10.xxxx/example
```

Enrich bibliographic metadata from ISBN:

```bash
python3 main.py biblio-enrich \
  --project autonomy_blockchain_paper \
  --doc-id doc_0001 \
  --isbn 9780262531559
```

If a DOI or ISBN is already stored in the bibliographic record, it can be omitted:

```bash
python3 main.py biblio-enrich --project autonomy_blockchain_paper --doc-id doc_0001
```

Bulk enrich all records that already contain DOI or ISBN metadata:

```bash
python3 main.py biblio-enrich --project autonomy_blockchain_paper --all
```

By default, enriched records remain `needs_review`. Use `--auto-verify` only when
you explicitly trust the matched external metadata:

```bash
python3 main.py biblio-enrich \
  --project autonomy_blockchain_paper \
  --doc-id doc_0001 \
  --isbn 9780262531559 \
  --auto-verify
```

External lookup is only used for bibliographic metadata. It is not used as
evidence for paper claims or LLM-generated academic content.

The app does not build indexes, query an LLM, or generate outlines yet.

## GitHub Workflow

We publish one functional prototype per module:

1. Implement the module.
2. Run automated tests.
3. Run a manual CLI smoke test.
4. Commit the module.
5. Push to GitHub.

See `docs/github_workflow.md` for the full checklist and first-publish commands.

## Troubleshooting

If `python3` is not available, try:

```bash
python --version
```

If dependencies are missing, make sure the virtual environment is active and reinstall:

```bash
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

See `docs/architecture.md` for the full architecture and module roadmap.
