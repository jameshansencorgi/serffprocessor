# SERFF Intel — Parallel Work Brief for Codex (Path 2)

**Context.** We split the MVP backlog from `docs/serff_catalogue_mvp_review.md` (sections 3–9) into two paths that run concurrently with **disjoint file ownership** so there are no merge conflicts. Claude owns **Path 1 (extraction correctness & catalogue contract)**. You (Codex) own **Path 2 (operability, persistence & tooling)** described below.

Repo root: `/Users/jameshansen/thecleaners/Corgi by James/serff-intel`. Tests: `.venv/bin/pytest -q` (currently 15 passing). Work test-first. The project uses thin CLI/service layers, fat services, focused modules, evidence-first extraction.

---

## Hard file boundaries (do not cross)

**You (Path 2) own and may edit:**
`serff_intel/pipeline.py`, `serff_intel/models.py`, `serff_intel/export.py`, `serff_intel/cli.py`, `serff_intel/services.py`, `serff_intel/storage/db.py`, `serff_intel/ingest/*`, `serff_intel/parsing/text_extract.py`, `pyproject.toml`, `README.md`, `tests/conftest.py`, `tests/test_pipeline.py`, and new `tests/test_ops_*.py`.

**Do NOT edit (Path 1 / Claude owns):**
`serff_intel/extract/*` (schemas, rate_impact, actuarial_reasons, objections, entities, context, fact_keys, enums) — you may **import** from them but not modify. `docs/fact_catalogue.{yml,md}`. `tests/test_catalogue_reconciliation.py` and new `tests/test_extract_*.py`.

**Excluded from BOTH paths right now:** `serff_intel/extract/tables.py` and table needs_review logic — the human is actively editing it. Table reliability work (CH6 / patch set D / Step 4) is deferred until that lands.

---

## Interface contract (provided by Path 1 — code against these)

- `serff_intel.extract.schemas.EvidenceFact` carries `fact_key: str | None` and `review_reason: str | None` (in addition to existing role/coverage/scope/unit/needs_review).
- `serff_intel.extract.fact_keys.canonical_fact_key(fact_type: str) -> str | None` — maps extractor `fact_type` → catalogue `fact_key`.
- `serff_intel.extract.enums` exposes controlled sets: `ROLES`, `UNITS`, `SUPERSESSION_STATUSES`, `TABLE_KINDS`, `EXTRACTION_METHODS`, `REVIEW_REASONS`. Use these for DB-side validation instead of inventing your own.
- Pure functions (signatures stable; Claude fills in the bodies): `classify_objection_topic(text: str) -> str`, `split_objection_and_response(text: str) -> tuple[str, str | None]`, `normalize_disposition(raw: str | None) -> str | None`. Wire these into the pipeline; if a function isn't landed yet, stub the call site behind a feature flag and leave a TODO referencing this brief.

If you need a new field or function on the extraction side, **request it** — don't add it to `extract/*` yourself.

---

## Path 2 tasks (priority order)

### P2.1 — Persist & export `fact_key` + `review_reason` (CH3, patch set A1–A4, Step 1)
- Add `fact_key` and `review_reason` columns to `ExtractedFact` (`models.py`).
- Populate them in `pipeline.py` from the `EvidenceFact` DTO (the values already flow on the DTO; today export *derives* `fact_key` — switch to the persisted column).
- Export `fact_key` from the column in every fact CSV.
- **DB-level test:** every stored high-value fact (rate change / LCM / provision) has a non-null catalogue `fact_key`; unmapped facts get `fact_key="unknown"` and `needs_review=True`.

### P2.2 — Decompose `process_pending` into typed stages + explicit transactions (CH1, PY2)
- Split into `parse_attachment` / `classify_attachment` / `persist_pages` / `extract_facts` / `extract_tables` / `persist_extraction_results` / `index_attachment`, each returning a typed result and unit-testable without full DB/FTS setup.
- Per-attachment `with session.begin():`; keep FTS rebuild outside the per-attachment transaction or make it per-attachment.
- Do not delete prior good extraction rows until the new result is ready (or write a new run and mark prior rows superseded).
- **Tests:** a failure after page parse but before fact persistence leaves prior committed attachments intact; reprocessing leaves no duplicate rows.

### P2.3 — `processing_error` table + per-stage exception boundaries (CH9, PY1, patch set B)
- Table fields: `run_id, filing_id, attachment_id, stage, exception_type, message, traceback_hash, retryable, created_at`.
- Wrap each stage; a forced extractor exception records one error and continues to the next attachment, preserving already-parsed pages.
- **Tests:** mocked parser/extractor exceptions record exactly one error row and do not halt the batch; retry clears/supersedes prior errors.

### P2.4 — Operational CLI + scale hygiene (CH8, PY9, patch set B4, Step 5)
- `process-pending --limit N`, `--serff SERFF_ID`, `--dry-run`, `--fail-fast`; `--log-level`; `summary --errors`.
- Incremental FTS (only changed attachments) with an explicit full-rebuild flag.
- Replace per-filing N+1 count queries in release building with grouped aggregates.
- **Tests:** `--limit 1` processes exactly one; `--serff X` touches only X; `--dry-run` creates no pages/facts/tables.

### P2.5 — Source metadata normalization (CH7, Step 3)
- Add `filing_source_metadata` and `attachment_source_metadata`; populate in **both** comp-search and S3-manifest import paths (section, form name, form number, TOI code, product name, QA status, download URL, expected vs downloaded counts, pulled timestamp).
- `attachments.csv` surfaces section/form name/form number; summary reports expected-vs-downloaded.

### P2.6 — Migrations / schema versioning (CH2, Step 5)
- `schema_version` table + Alembic (or a small versioned runner). CLI fails clearly when DB schema is older than code. Test migrates an older SQLite forward.

### P2.7 — Tooling & test taxonomy (PY4, PY5, PY6, PY10, patch set E)
- Add `ruff` + `mypy` (+ `types-PyYAML`) to `pyproject.toml` with config (Ruff `E,F,I,UP,B,SIM,RET,RUF`; mypy moderate→strict). README CI block.
- pytest markers `unit/smoke/integration`; default `pytest -q` runs unit/smoke only; gate real-SERFF/`/private/tmp` tests behind `SERFF_INTEL_INTEGRATION=1`. Move shared setup into `conftest.py` fixtures; use `monkeypatch.setenv` for env/config tests.
- Module loggers (`serff_intel.pipeline/ingest/extract`) + `--log-level`.

### P2.8 — Wire Path 1 logic (H4 wiring)
- Replace hardcoded `topic="general"` and the always-NULL `company_response_text` in the objection insert with `classify_objection_topic` / `split_objection_and_response`.
- Map `Filing.status` through `normalize_disposition` on import.

---

## Coordination rules
- Run `.venv/bin/pytest -q` before/after each task; keep it green.
- If you must touch a Path 1 file, stop and request the change instead.
- Commit in small task-sized chunks with the task ID (P2.x) in the message.
- The catalogue's `default_provenance_fields` and `role_enum` are a shared contract — Path 1 only *adds* to them; if you read them, don't assume removals.
