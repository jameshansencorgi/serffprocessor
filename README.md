# SERFF Intel

SERFF Intel is a LOCUS-style prototype for turning public SERFF filing files into a local, searchable, evidence-backed database.

It follows the same broad pattern as LOCUS:

- preserve raw source material and provenance
- normalize messy source metadata into a harmonized access layer
- parse/OCR heterogeneous documents
- classify documents
- extract structured facts with evidence
- build keyword/vector-ready search chunks
- track coverage and processing quality

The first version deliberately makes manual import excellent. If automated SERFF download is blocked or inappropriate, drop filing folders into `data/raw/filings/{state}/{serff_tracking_number}/` and process them locally.

## Install

```bash
cd serff-intel
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Quick Start

```bash
serff-intel init-db
serff-intel import-folder data/raw/filings/TX/ACME-133700001
serff-intel process-pending
serff-intel summary
serff-intel facts --serff ACME-133700001
serff-intel search "commercial auto nuclear verdicts trucking"
```

You can also run without installing the console script:

```bash
python -m serff_intel.cli init-db
python -m serff_intel.cli import-folder data/raw/filings/TX/ACME-133700001
python -m serff_intel.cli process-pending
python -m serff_intel.cli search "social inflation"
```

## Folder Format

Each filing folder can contain a `metadata.json` file and any supported attachments:

```text
data/raw/filings/TX/ACME-133700001/
  metadata.json
  Actuarial_Memorandum.pdf
  Approval_Letter.pdf
  Rate_Manual.xlsx
```

Supported first-pass attachment types:

- `.pdf`
- `.txt`
- `.md`
- `.csv`
- `.docx`
- `.xlsx`
- `.xlsm`

## Database Layers

Raw corpus:

- `raw_s3_object`
- `raw_filing_bundle`

Harmonized access layer:

- `filing`
- `attachment`
- `document_page`

Evidence and intelligence:

- `extracted_fact`
- `regulator_objection`
- `embedding_chunk`
- `coverage_snapshot`

Search:

- SQLite FTS5 virtual table `filing_fts`

## Code Architecture

The package follows the Doghouse thin-layer pattern:

- `cli.py` is mechanical command handling only.
- `services.py` owns orchestration and is the main application boundary.
- `dtos.py` contains typed service return values.
- `models.py` is pure SQLAlchemy schema.
- `ingest/`, `parsing/`, `classify/`, `extract/`, and `search/` are focused implementation modules behind the service layer.

## Current Extracted Facts

The MVP extracts:

- requested, approved, indicated, and selected rate changes
- written premium impact
- loss trend
- expense provision
- profit provision
- social inflation
- nuclear verdicts
- litigation
- frequency/severity
- telematics
- new ventures
- trucking/commercial auto
- regulator objection snippets

Every extracted fact stores confidence, source attachment, page number where available, extraction method, and evidence text.

## S3 Method

For a real S3-backed SERFF database, keep S3 immutable and use this flow:

1. Create an S3 inventory or manifest of keys, sizes, ETags, timestamps, and source prefixes.
2. Load that into `raw_s3_object`.
3. Group objects into `raw_filing_bundle` rows by state and SERFF tracking number.
4. Cache objects locally only for parsing.
5. Write normalized rows into `filing` and `attachment`.
6. Run parsers, classifiers, extractors, and search indexing.

That gives you a reproducible raw corpus plus a clean SERFF access layer.

The prototype includes a manifest importer for this path:

```bash
serff-intel import-s3-manifest s3_manifest.csv
```

Required manifest columns:

```csv
state,serff_tracking_number,bucket,key,local_path
TX,ACME-133700001,my-serff-bucket,tx/ACME-133700001/Actuarial_Memorandum.pdf,/local/cache/Actuarial_Memorandum.pdf
```

Optional columns include `company_name`, `line_of_business`, `file_type`, `content_type`, and `etag`.

## Tests

```bash
pytest -q
```

## Near-Term TODOs

- Add S3 manifest import command.
- Add optional Tesseract OCR fallback for scanned PDFs.
- Add pgvector/LanceDB vector index.
- Add richer table extraction for XLSX rate exhibits.
- Add review UI for low-confidence facts.
- Add coverage snapshots by state, line of business, and date range.
