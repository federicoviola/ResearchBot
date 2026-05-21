# Academic Paper CLI Architecture

## 1. General Architecture

This system is a CLI-first, folder-based academic paper production assistant. Each paper project is a self-contained directory containing configuration, source dataset files, derived artifacts, outputs, and execution state.

The closed bibliographic dataset is the authority. LLM calls in later modules must be composed only from project instructions plus retrieved corpus chunks. The LLM may analyze, synthesize, organize, and draft, but it must not introduce external claims, invented references, or unsupported bibliography entries.

The architecture is intentionally modular:

- Module 1 creates and validates project structure.
- Module 2 registers source PDFs.
- Module 3 extracts text and metadata.
- Module 3.5 manages curated bibliographic metadata.
- Module 3.6 enriches bibliographic metadata from external identifier APIs.
- Module 4 builds a searchable local index.
- Module 5 performs grounded dataset querying.
- Module 6 generates grounded outlines.

Modules communicate through files and state records, not through a monolithic runtime service. This keeps the MVP local-first, testable, and easy to inspect.

## 2. Folder Structure

```text
academic-paper-cli/
├── academic_paper_cli/
│   ├── __init__.py
│   ├── cli.py
│   ├── models.py
│   ├── bibliography_manager.py
│   ├── bibliography_enrichment.py
│   ├── dataset_manager.py
│   ├── pdf_processor.py
│   └── project_manager.py
├── docs/
│   └── architecture.md
├── projects/
│   └── <paper_project>/
│       ├── config/
│       │   ├── project.yaml
│       │   ├── system_prompt.md
│       │   ├── writing_style.md
│       │   ├── citation_style.yaml
│       │   └── skills/
│       │       └── outline_design.md
│       ├── dataset/
│       │   ├── pdf/
│       │   ├── txt/
│       │   ├── metadata/
│       │   ├── bibliography/
│       │   └── index/
│       ├── outputs/
│       │   ├── outlines/
│       │   ├── notes/
│       │   ├── logs/
│       │   └── reports/
│       └── state/
│           ├── ingestion_state.json
│           ├── index_state.json
│           └── run_history.json
├── tests/
│   └── test_project_manager.py
└── main.py
```

## 3. Project Configuration Design

`config/project.yaml` stores paper-level behavior:

```yaml
name: autonomy_blockchain_paper
title: Autonomy Blockchain Paper
description: ""
research_question: ""
language: en
llm:
  provider: openai_compatible
  base_url: http://localhost:11434/v1
  model: configure-me
  api_key_env: OPENAI_API_KEY
  temperature: 0.2
  max_tokens: 1800
retrieval:
  top_k: 8
  chunk_size: 900
  chunk_overlap: 150
  embedding_model: sentence-transformers/all-MiniLM-L6-v2
grounding:
  require_sources: true
  allow_external_knowledge: false
  unsupported_answer: The dataset does not contain enough information to answer this without unsupported claims.
```

Other configurable files:

- `config/system_prompt.md`: global closed-corpus behavior.
- `config/writing_style.md`: tone, genre, and academic style instructions.
- `config/citation_style.yaml`: citation and bibliography policy.
- `config/skills/*.md`: reusable instruction modules selected explicitly by CLI flags in later modules.

LLM provider choices remain OpenAI-compatible by interface. Ollama, LM Studio, vLLM, and hosted OpenAI-compatible APIs can be represented by changing `base_url`, `model`, and `api_key_env`.

## 4. CLI Command Design

Implemented:

```bash
python3 main.py init-project --name autonomy_blockchain_paper
python3 main.py status --project autonomy_blockchain_paper
python3 main.py add-pdf --project autonomy_blockchain_paper --file ./sources/castoriadis.pdf
python3 main.py add-pdfs --project autonomy_blockchain_paper --path ./sources --recursive
python3 main.py list-docs --project autonomy_blockchain_paper
python3 main.py ingest --project autonomy_blockchain_paper
python3 main.py biblio-init --project autonomy_blockchain_paper
python3 main.py biblio-list --project autonomy_blockchain_paper
python3 main.py biblio-show --project autonomy_blockchain_paper --doc-id doc_0001
python3 main.py biblio-set --project autonomy_blockchain_paper --doc-id doc_0001 --type book --title "..." --author "Family, Given" --year 2024 --publisher "..." --verified
python3 main.py biblio-validate --project autonomy_blockchain_paper
python3 main.py biblio-export --project autonomy_blockchain_paper --format bibtex
python3 main.py biblio-enrich --project autonomy_blockchain_paper --doc-id doc_0001 --doi 10.xxxx/example
python3 main.py biblio-enrich --project autonomy_blockchain_paper --doc-id doc_0001 --isbn 9780262531559
python3 main.py biblio-enrich --project autonomy_blockchain_paper --all
```

Designed for later modules:

```bash
python3 main.py build-index --project autonomy_blockchain_paper
python3 main.py index-status --project autonomy_blockchain_paper
python3 main.py query --project autonomy_blockchain_paper "What does the dataset say about autonomy?"
python3 main.py outline --project autonomy_blockchain_paper --skill outline_design
python3 main.py list-skills --project autonomy_blockchain_paper
python3 main.py add-skill --project autonomy_blockchain_paper --name philosophical_argumentation
```

## 5. Module Map

| Module | Responsibility | Commands | Current Status |
|---|---|---|---|
| 1. Project Manager | Create folders, defaults, state files, validate structure, status | `init-project`, `status` | Implemented |
| 2. Dataset Manager | Copy/register PDFs, bulk add PDFs, avoid duplicates, document IDs | `add-pdf`, `add-pdfs`, `list-docs` | Implemented |
| 3. PDF Processor | Extract text and metadata, update ingestion state | `ingest` | Implemented |
| 3.5. Bibliographic Metadata Manager | Create, curate, validate, and export citation metadata | `biblio-init`, `biblio-list`, `biblio-show`, `biblio-set`, `biblio-validate`, `biblio-export` | Implemented |
| 3.6. Bibliographic Metadata Enrichment | Enrich citation metadata from DOI/ISBN APIs, individually or in bulk | `biblio-enrich` | Implemented |
| 4. Index Builder | Chunk text, embed chunks, store vector index | `build-index`, `index-status` | Designed only |
| 5. Query Engine | Retrieve chunks, compose grounded prompts, call LLM | `query` | Designed only |
| 6. Outline Generator | Retrieve corpus context, apply skill, save grounded outline | `outline` | Designed only |

## 6. Data Models

Implemented dataclass models:

- `LLMProviderConfig`
- `RetrievalConfig`
- `GroundingPolicy`
- `ProjectConfig`
- `ProjectPaths`
- `ProjectStatus`

- `DocumentRecord`: document ID, original source path, stored PDF path, checksum, registration date.
- `BulkAddPdfResult`: summary for bulk PDF registration.
- `IngestionResult`: document ID, extraction status, text path, metadata path, page and word counts.
- `BibliographicAuthor`: structured citation author name.
- `BibliographicRecord`: curated bibliographic metadata for one document.
- `BibliographyValidationResult`: citation-readiness validation result.
- `BibliographyEnrichmentResult`: result of external DOI/ISBN enrichment.

Later modules should add:

- `ChunkRecord`: chunk ID, document ID, page range, text span, index backend ID.
- `RetrievalResult`: chunk text, score, document metadata, source reference.
- `LLMRunRecord`: prompt hash, retrieved chunk IDs, provider, model, output path.

## 7. Prompt Composition Strategy

Later LLM modules must compose prompts in this order:

1. `config/system_prompt.md`
2. Structured summary of `config/project.yaml`
3. `config/writing_style.md`
4. `config/citation_style.yaml`
5. Selected `config/skills/<skill>.md`, if provided
6. Retrieved dataset chunks with source IDs
7. User command or task

The prompt must include hard grounding instructions:

- Answer only from retrieved chunks.
- Include source references for every substantive claim.
- Do not invent citations or bibliography entries.
- State when evidence is insufficient.
- Keep source mapping visible in outline sections and answers.

Outputs should save the retrieved chunk IDs and prompt metadata to `outputs/logs/` or `state/run_history.json` for auditability.

## 8. Testing Strategy

Testing proceeds module by module:

- Module 1: create projects in temporary directories, assert required paths and default files, validate status behavior, reject unsafe project names.
- Module 2: verify duplicate detection using file checksums and stable document IDs.
- Module 3: run PDF extraction against small fixture PDFs and assert text/metadata/state outputs.
- Module 3.5: create bibliography templates, set curated metadata, validate required fields, export BibTeX and CSL-JSON.
- Module 3.6: enrich metadata using fake DOI/ISBN API clients, without depending on internet during tests.
- Module 4: test deterministic chunking, index metadata, and reindex behavior.
- Module 5: test retrieval and prompt composition with a fake LLM provider that refuses unsupported answers.
- Module 6: test outline output schema and source mapping using fixture chunks.

The current tests use `unittest` so they run without extra dependencies, and they remain discoverable by `pytest` later.

## 9. Implementation Roadmap

1. Module 1: project manager, default configuration, validation, status command.
2. Module 2: add PDF registration with SHA-256 duplicate checks in `ingestion_state.json`.
3. Module 3: extract text/metadata with PyMuPDF and update `ingestion_state.json`.
4. Module 3.5: curate bibliographic metadata and export verified records.
5. Module 3.6: enrich bibliographic metadata from DOI/ISBN sources.
6. Run tests and manually validate bibliography readiness.
7. Module 4: chunk texts, embed chunks, persist vector index and chunk metadata.
8. Module 5: retrieve chunks, compose closed-corpus prompt, call configurable LLM provider.
9. Module 6: generate source-mapped paper outline and save Markdown/JSON outputs.

## 10. Implemented Code

Implemented module code lives in:

- `academic_paper_cli/project_manager.py`
- `academic_paper_cli/dataset_manager.py`
- `academic_paper_cli/pdf_processor.py`
- `academic_paper_cli/bibliography_manager.py`
- `academic_paper_cli/bibliography_enrichment.py`
- `academic_paper_cli/models.py`
- `academic_paper_cli/cli.py`
- `main.py`

No indexing, query, or outline commands are implemented yet.

## 11. Instructions to Run and Test

Run the tests:

```bash
python3 -m unittest
```

Create a project:

```bash
python3 main.py init-project --name autonomy_blockchain_paper
```

Check status:

```bash
python3 main.py status --project autonomy_blockchain_paper
```

Add and list a PDF:

```bash
python3 main.py add-pdf --project autonomy_blockchain_paper --file ./sources/castoriadis.pdf
python3 main.py add-pdfs --project autonomy_blockchain_paper --path ./sources --recursive
python3 main.py list-docs --project autonomy_blockchain_paper
```

Ingest registered PDFs:

```bash
python3 main.py ingest --project autonomy_blockchain_paper
```

Create, validate, and export bibliographic metadata:

```bash
python3 main.py biblio-init --project autonomy_blockchain_paper
python3 main.py biblio-set --project autonomy_blockchain_paper --doc-id doc_0001 --type book --title "Title" --author "Family, Given" --year 2024 --publisher "Publisher" --verified
python3 main.py biblio-validate --project autonomy_blockchain_paper
python3 main.py biblio-export --project autonomy_blockchain_paper --format bibtex
```

Enrich bibliographic metadata from external identifier APIs:

```bash
python3 main.py biblio-enrich --project autonomy_blockchain_paper --doc-id doc_0001 --doi 10.xxxx/example
python3 main.py biblio-enrich --project autonomy_blockchain_paper --doc-id doc_0001 --isbn 9780262531559
python3 main.py biblio-enrich --project autonomy_blockchain_paper --all
```

External metadata enrichment is limited to citation metadata and does not expand
the evidence corpus for LLM analysis.

If your shell has `python` mapped to Python 3, the same commands work with `python main.py ...`.
