# SERFF Fact Catalogue & Extraction — MVP Adversarial Review

**Date:** 2026-06-28
**Reviewer:** automated adversarial review (7 dimensions, per-finding verification), re-baselined against the live working tree.
**Scope:** `docs/fact_catalogue.{md,yml}`, `serff_intel/extract/*`, `models.py`, `pipeline.py`, `export.py`, sample corpus.

> ⚠️ **Caveat — moving target.** The schema and extractors were being edited *during* this review. Findings below are re-verified against the working tree as of the date above. Tests currently pass (`pytest -q` → 10 passed, including the untracked catalogue reconciliation tests). Anything marked **DONE** landed during the review session; **OPEN** items remain.

---

## 1. What already landed (verify, don't redo)

| Area | Evidence |
| --- | --- |
| `EvidenceFact` is now a full provenance DTO (unit/coverage/role/scope/territory/needs_review + table locator + supersession) | `serff_intel/extract/schemas.py:6-35` |
| `extracted_fact` is self-describing; `extracted_table` + `extracted_table_cell` tables exist | `serff_intel/models.py:130-201` |
| Role inference for rate-change / LCM / profit facts; `scope="overall"`; `needs_review` when role ambiguous | `serff_intel/extract/rate_impact.py:27-91,94-116` |
| Coverage inference (AL/APD/BI/PD…) and table-candidate extraction | `serff_intel/extract/context.py`, `serff_intel/extract/tables.py` |
| Exports carry role/coverage/scope/unit + emit `extracted_tables.csv` / `extracted_table_cells.csv` | `serff_intel/export.py:147-182,244-309` |

This clears the original "schema can't cash the catalogue's checks" class of findings. What remains is **correctness, reconciliation, scope, and doc hygiene.**

---

## 2. Open gaps — prioritized

### CRITICAL

**C1 — Catalogue keys and extractor fact-types are different vocabularies (the catalogue's stated purpose is unreachable).**
`fact_catalogue.md:3` frames the catalogue as the bridge from observations to a relational model, keyed by `fact_key`. But there is no `fact_key` on emitted facts and the names diverge:

| catalogue `fact_key` (yml) | extractor `fact_type` (code) |
| --- | --- |
| `requested_overall_rate_change` | `requested_rate_change` |
| `approved_overall_rate_change` | `approved_rate_change` |
| `indicated_rate_change` | `indicated_rate_level_change` |
| `selected_rate_change` | `selected_rate_level_change` |
| `frequency_trend` / `severity_trend` | `frequency` / `severity` (keyword tagger) |

→ **Add a canonical `fact_key` map, set it on every fact, surface it in exports, and add a conformance test that every mapped key exists in the catalogue.** *(Status: being implemented.)*

**C2 — Numeric extractors grab "first/last number in a fixed char window" and silently drop decreases.**
`rate_impact.py:8-21` patterns take the first percent after the label; a clause like "credibility 60%" between label and figure is captured instead. `LCM_RE` + `value = decimals[-1]` (`rate_impact.py:23,60`) takes the last decimal in a 160-char window. **Parenthetical negatives `(5.0%)` — the standard decrease notation — are missed** (regex requires a literal `-`). The 9-line sample is too clean to expose any of this. *(Parenthetical-negative handling: being implemented.)*

**C3 — Two truths never meet; the derived fact and an extracted fact reach no export.**
`Filing.rate_impact_requested/approved` come only from `metadata.json`; the regex rate-change facts live in `extracted_fact`; nothing reconciles them. `requested_approved_rate_gap` (yml, importance critical) is computed nowhere. `written_premium_impact` is extracted (`rate_impact.py:14`) but referenced in **zero** export buckets (`export.py:21-24`). *(Gap derivation + written-premium export bucket: being implemented.)*

### HIGH

**H1 — Ratemaking assumptions catalogued as numbers, stored as words.** `actuarial_reasons.py:6-17` stores the matched keyword (`fact_value="frequency"`), no number, yet `frequency_trend`/`severity_trend`/`credibility` are `datatype: decimal, importance: critical`. Either write numeric extractors or demote to narrative tags.

**H2 — Confidence is decorative, so the review queue is mis-sorted.** Confidence is a per-extractor constant (0.78/0.72/0.70); `export_review_csv` orders by confidence (`export.py:136`) = by extractor identity. Now that `needs_review` exists, sort the queue by `needs_review` then confidence. *(Being implemented.)*

**H3 — Coverage is page-level, not value-level.** `infer_coverage` tags every fact on a page with the union `"AL/APD"` (`pipeline.py:105-107`), so a specific LCM can't be attributed to AL vs APD. Fine as a fallback; don't treat as per-fact truth.

**H4 — Disposition & objections are pass-through.** `Filing.status` is the raw `"Approved"` string (no controlled-vocab mapping); objection `topic` is hardcoded `"general"` (`pipeline.py:149`), `company_response_text` is always NULL, and `OBJECTION_RE` (`objections.py:8`) fires on "no objection" and merges concerns.

---

## 3. Remove / Defer from the MVP catalogue (over-scope)

The YAML enumerates ~74 facts (27 "critical") but most are `status: missing` with no code. Explicitly mark deferred:

- **`rating_factors`, `rating_algorithm` (formula_step, worked_example), `caps_floors_rounding`** — full rating-plan reconstruction. **REMOVE from MVP.**
- **`territory_definitions`** (ZIP lists, remaps) — **DEFER.**
- **Rate-impact distribution** (`policyholders_affected`, `impact_band_count`, min/max individual impact) — **DEFER.**
- **Downgrade `importance: critical`** on facts not yet reliably extractable (LDF values, freq/sev trend numbers, credibility, permissible loss ratio) to a `target` marker.

---

## 4. Doc hygiene

- `fact_catalogue.md` still lists 11 normalized destination tables; only `extracted_fact` / `extracted_table` / `extracted_table_cell` exist — relabel real vs future.
- Split `normalized` into `extracted` vs `sourced_from_metadata`: Tier-0 fields (`line_of_business`, dates, `filing_type`) are never text-extracted (`entities.py`, `pipeline.py:262-265`) and go NULL on the S3-manifest path.
- The corpus is one 9-line memo + one 7-line letter (`data/raw/filings/TX/ACME-133700001/`) with zero LCM/table text. Add realistic fixtures (Exhibit-G/LCM, trend exhibit, expense exhibit) so status claims are backed by a passing extraction.

---

## 5. The honest MVP critical path (~14 facts)

Filing spine (serff#, company, NAIC, state, LOB, filing_type, dates, disposition) → overall **requested/approved/indicated/selected** rate change *with role+scope* → **LCM** with role → **expense/profit provisions** with role → **loss trend** → **written premium impact** → regulator-objection snippet. Everything else: explicitly deferred.

---

## 6. Recommended next actions (ordered, low-risk first)

1. **C1** — `fact_key` canonical map + conformance test. *(in progress)*
2. **C3** — wire `written_premium_impact` into an export bucket; compute `requested_approved_rate_gap`. *(in progress)*
3. **C2** — handle `(x%)` negative notation in rate regexes. *(in progress)*
4. **H2** — re-sort review queue by `needs_review` then confidence. *(in progress)*
5. **H4 / H1** — disposition normalizer; honest demotion of keyword-only trend facts.
6. **Doc** — trim deferred groups; add realistic fixtures; relabel statuses.

---

## 7. Code health adversarial review

### Review basis

The `.claude/` directory exists but currently contains only empty subdirectories (`agents`, `commands`, `hooks`, `skills`), so there were no repo-local Claude coding skill files to apply directly. This review uses the repository's visible coding pattern instead: thin CLI/service layers, focused modules, evidence-first extraction, tests before trusting output, and explicit provenance.

The main LLM failure modes to avoid here are:

- **Regex theater:** broad regexes that look impressive but silently grab the wrong number.
- **Schema theater:** catalogue fields that exist in docs but are not persisted, exported, or tested.
- **Confidence theater:** constants like `0.78` that sort review queues but do not represent measured reliability.
- **Fixture theater:** toy tests that pass while real SERFF exhibits fail.
- **Architecture drift:** one pipeline function accreting parsing, classification, extraction, persistence, table detection, and indexing.

### Code health findings

#### CH1 — The pipeline function is doing too many jobs.

`process_pending` parses documents, deletes old rows, classifies documents, writes pages, makes parse decisions, writes text files, backfills filing metadata, extracts facts, persists tables/cells, creates objection rows, chunks text, classifies segments, writes embedding chunks, commits, and rebuilds FTS.

Risk: every future extractor increases blast radius. A table bug can break parsing; an objection bug can affect chunking; a retry can delete useful prior state.

Fix:
- Split into small orchestration steps:
  - `parse_attachment`
  - `classify_attachment`
  - `persist_pages`
  - `extract_facts`
  - `extract_tables`
  - `persist_extraction_results`
  - `index_attachment`
- Make each step return typed results and test those steps independently.

Acceptance criteria:
- `process_pending` is mostly orchestration, not extraction logic.
- Unit tests can run table extraction without database setup.
- Unit tests can run fact extraction without parsing or FTS.
- Failed attachment processing does not prevent already-processed attachments from remaining valid.

#### CH2 — There is no migration strategy, but the schema is changing quickly.

`init_db` uses `Base.metadata.create_all`, which is fine for a prototype but dangerous once real S3 filings are loaded. Schema additions such as `fact_key`, source metadata tables, or normalized fact tables will not backfill or migrate existing databases.

Risk: production-ish local databases become incompatible or silently miss columns. Re-running from scratch becomes the only migration path.

Fix:
- Add Alembic or a small versioned migration runner before full S3 ingestion.
- Add a `schema_version` table.
- Make CLI startup fail clearly if DB schema is older than code expectations.

Acceptance criteria:
- A test creates an older SQLite schema and migrates it forward.
- `serff-intel summary` reports schema version.
- No schema-changing PR lands without a migration.

#### CH3 — The evidence model and catalogue are still not fully joined.

`EvidenceFact.fact_key` exists in the dirty working tree, and reconciliation tests pass, but `ExtractedFact` still does not persist `fact_key`. That keeps the catalogue from becoming a load-bearing contract.

Risk: exports continue using extractor-local `fact_type`, while the catalogue evolves separately.

Fix:
- Add `fact_key` to `ExtractedFact`.
- Persist it in `pipeline.py`.
- Export it in every fact CSV.
- Add a DB-level test that every stored high-value fact has a catalogue key.

Acceptance criteria:
- `rate_changes.csv`, `loss_cost_multipliers.csv`, and `provisions.csv` include `fact_key`.
- Catalogue reconciliation test queries the database, not only DTOs.
- Unknown/unmapped facts are explicitly marked `fact_key=unknown` or routed to review.

#### CH4 — Confidence scores are hard-coded and should not drive workflow alone.

Extractors emit constants such as `0.78`, `0.72`, and `0.70`. Table confidence is heuristic. These are useful as rough metadata but not statistically calibrated.

Risk: the review queue can look mathematically precise while ranking extractor identity instead of real risk.

Fix:
- Treat confidence as `extractor_confidence`, not actuarial correctness.
- Add separate booleans/reasons:
  - `needs_review`
  - `review_reason`
  - `quality_flags`
- Sort review exports by `needs_review`, `review_reason`, and then confidence.

Acceptance criteria:
- Every `needs_review=true` row has a reason.
- Review export sorts review-required rows first.
- Confidence values are documented as heuristic, not calibrated probabilities.

#### CH5 — Tests are not realistic enough for extraction claims.

Current tracked fixtures are very small text files. The real downloaded sample revealed table-heavy PDFs and edge cases that toy fixtures do not cover.

Risk: tests pass while the pipeline fails on common SERFF artifacts: Exhibit G, ROE/profit exhibits, trend exhibits, LDF exhibits, and scanned PDFs.

Fix:
- Add small realistic text fixtures derived from extracted SERFF page text:
  - Exhibit G / LCM page
  - ROE/profit page
  - trend selection page
  - LDF table page
  - objection/response page
  - scanned/no-text PDF placeholder
- Keep fixtures tiny, but preserve the actual label/value patterns.

Acceptance criteria:
- Parenthetical decrease `(5.0%)` is tested.
- Indicated/selected/prior/rounded/offset LCM roles are tested.
- Table row/column labels from realistic exhibits are tested.
- No extractor status is called `partial` or `normalized` without fixture coverage.

#### CH6 — Table extraction is useful but still too heuristic for actuarial grids.

The current table parser is line-based and infers rectangularity from text extraction. That is good enough for triage, but not enough for rating factor grids, territory grids, or AOI x territory tables.

Risk: a PDF extraction artifact can create a plausible but wrong table. The database then looks queryable while the grid is corrupted.

Fix:
- Keep current table extraction as `text_table_candidate`.
- Add a parser source field: `pdfplumber_table`, `text_line_heuristic`, `excel_sheet`, `docx_table`.
- Prefer structured table APIs for Excel, DOCX, and `pdfplumber.extract_tables()`.
- Promote cells to analytical facts only when table source and structure meet stricter criteria.

Acceptance criteria:
- `extracted_table` records parser source.
- Excel/DOCX tables bypass line-heuristic parsing.
- Cell-derived analytical facts require a table quality threshold and carry `table_cell_id`.

#### CH7 — Source metadata normalization is still postponed.

SERFF-native fields such as section, form name, form number, download URL, TOI code, product name, QA status, expected/downloaded attachments, and pulled timestamp are still mostly raw JSON.

Risk: QA and corpus coverage questions become hard to answer: "which filings are missing attachments?", "which section did this exhibit come from?", "what product name did SERFF show?"

Fix:
- Add `filing_source_metadata`.
- Add `attachment_source_metadata`.
- Populate them in both comp-search and manifest import paths.

Acceptance criteria:
- `attachments.csv` includes SERFF section/form name/form number.
- Summary can report expected vs downloaded attachments.
- Imported comp-search and S3-manifest rows normalize the same core metadata fields.

#### CH8 — Batch processing will not scale cleanly to S3 volume yet.

The current processing loop commits per attachment and rebuilds all FTS after processing. Release building performs repeated per-filing count queries.

Risk: this will be slow and fragile on thousands of filings. A single rerun does unnecessary global work.

Fix:
- Add batch size controls and resume markers.
- Rebuild/index only changed attachments unless a full rebuild is requested.
- Replace repeated count queries with grouped aggregate queries.
- Add processing run metadata.

Acceptance criteria:
- CLI supports `process-pending --limit N`.
- Processing records a run ID and per-attachment status.
- FTS rebuild can run incrementally or full.
- Release building uses aggregate queries, not per-filing N+1 counts.

#### CH9 — Error handling is too coarse for production-ish ingestion.

Parsing failures are stored at the attachment level, but extractor/table errors are not isolated. A bug in one extractor can fail the whole attachment. There is no structured error table.

Risk: one bad PDF or unexpected text pattern can block a large batch or hide why data is missing.

Fix:
- Add `processing_error` table with stage, attachment, exception type, message, traceback hash, and retryable flag.
- Wrap stages independently.
- Keep partial successful outputs when later stages fail, marked with stage status.

Acceptance criteria:
- A forced extractor exception records an error and continues to next attachment.
- Summary reports parse, extraction, table, and export errors separately.
- Retrying an attachment clears/replaces prior errors for that attachment.

#### CH10 — Several values use free-form strings where enums would prevent drift.

Fields such as `document_class`, `extraction_route`, `value_tier`, `role`, `supersession_status`, `table_kind`, and `parse_status` are strings. The catalogue defines some enums, but code does not enforce them.

Risk: small spelling changes create hidden categories and broken downstream filters.

Fix:
- Centralize enums in Python modules or load them from the catalogue.
- Validate DTOs before persistence.
- Add tests for all known enum values.

Acceptance criteria:
- Invalid role or supersession status raises in tests.
- Exported values are drawn from controlled sets.
- Catalogue enum and Python enum cannot diverge silently.

### Improvement roadmap

#### Step 1 — Stabilize contracts before more extraction

Implement:
- Persist/export `fact_key`.
- Add `review_reason`.
- Sort review exports by `needs_review`.
- Add enum validation for `role`, `supersession_status`, `table_kind`, `extraction_route`.

Tests:
- Database-level catalogue reconciliation.
- Invalid enum rejection.
- Review CSV ordering.

#### Step 2 — Make current extractors safer

Implement:
- Parenthetical negative parsing.
- Role-specific LCM/profit extraction patterns.
- Written premium export.
- Requested-approved gap derivation.
- Numeric trend/credibility extractors or demote keyword facts.

Tests:
- Parenthetical decrease fixture.
- Indicated/selected/prior/rounded/offset LCM fixture.
- Requested vs approved reconciliation fixture.
- Written premium impact export fixture.

#### Step 3 — Normalize source metadata

Implement:
- `filing_source_metadata`.
- `attachment_source_metadata`.
- Comp-search and S3 manifest population.

Tests:
- Comp-search run populates section/form name/form number.
- S3 manifest importer populates source metadata consistently.
- Attachment coverage/QA summary works from normalized columns.

#### Step 4 — Make table extraction honest

Implement:
- Table parser source.
- Structured Excel/DOCX table extraction path.
- PDF table extraction path using table APIs before line heuristics.
- Cell-to-fact linking for high-confidence table-derived facts.

Tests:
- Excel fixture creates table/cell rows without line heuristics.
- PDF text fixture preserves row/column labels.
- Low-confidence table stays review-flagged.
- High-confidence table-derived fact includes `table_cell_id`.

#### Step 5 — Prepare for S3-scale operation

Implement:
- Migrations/schema versioning.
- Processing runs and stage-specific errors.
- `process-pending --limit`.
- Incremental FTS indexing.
- Aggregate release queries.

Tests:
- Migration from previous schema.
- Forced parsing/extraction error does not halt batch.
- Incremental processing only touches pending/failed attachments.
- Release building query count does not grow linearly with filings.

### Definition of healthy MVP

The MVP is code-healthy when:

- Every exported high-value fact has `fact_key`, `role` where applicable, provenance, and review status.
- The catalogue describes what code actually extracts, not aspirational future scope.
- Review queues prioritize actual risk.
- Realistic fixtures cover the patterns we claim to support.
- Table cells are useful for QA, but only promoted to actuarial facts when structure is trustworthy.
- Schema changes are migrated, not handled by deleting the database.
- Batch processing can fail partially, resume, and explain what happened.

---

## 8. Online Python/tooling review — missed pitfalls and action plan

This section cross-checks the current codebase against current primary Python ecosystem guidance:

- Python exceptions and cleanup: <https://docs.python.org/3/tutorial/errors.html>
- Python logging: <https://docs.python.org/3/howto/logging.html>
- SQLAlchemy transactions: <https://docs.sqlalchemy.org/en/20/orm/session_transaction.html>
- Pydantic strict mode: <https://pydantic.dev/docs/validation/latest/concepts/strict_mode/>
- pytest `tmp_path`: <https://docs.pytest.org/en/stable/how-to/tmp_path.html>
- pytest `monkeypatch`: <https://docs.pytest.org/en/stable/how-to/monkeypatch.html>
- Ruff rules: <https://docs.astral.sh/ruff/rules/>
- mypy type hints: <https://mypy.readthedocs.io/en/stable/cheat_sheet_py3.html>

### PY1 — Exceptions should be stage-specific, logged, and resumable

Current risk:
- Parsing catches broad PDF/DOCX/XLSX exceptions and returns string failures, but extraction/table/indexing errors are not isolated.
- `process_pending` can fail mid-attachment without recording which stage failed.
- There is no structured error table.

Why this matters:
- Python's own guidance is to catch specific exceptions where possible, let unexpected exceptions propagate or log/re-raise them, and use cleanup actions for external resources. For large S3 batches, "one bad filing stops the run" is not acceptable, but neither is swallowing errors.

Action:
1. Add `processing_error` table:
   - `id`
   - `run_id`
   - `filing_id`
   - `attachment_id`
   - `stage`
   - `exception_type`
   - `message`
   - `traceback_hash`
   - `retryable`
   - `created_at`
2. Wrap these stages independently:
   - parse
   - classify
   - extract_facts
   - extract_tables
   - persist
   - index
3. On expected parse failures, record a non-fatal error and mark attachment `parse_status=failed`.
4. On unexpected extractor failures, record error, mark extraction failed, continue to next attachment, and preserve pages already parsed.

Acceptance tests:
- A mocked PDF parser exception creates one `processing_error` row and does not stop the batch.
- A mocked extractor exception preserves `document_page` rows but records `stage=extract_facts`.
- Reprocessing an attachment clears or supersedes old errors for that attachment.

### PY2 — Replace implicit transaction behavior with explicit transaction scopes

Current risk:
- `process_pending` commits once per attachment after many unrelated operations.
- If one stage fails, it is unclear which rows are durable and which were rolled back.
- Table deletion and re-insertion happens before extraction completes.

Why this matters:
- SQLAlchemy 2.0 documents explicit transaction demarcation with `Session.begin()` as the normal way to make database unit-of-work boundaries clear.

Action:
1. Make each attachment a transaction:
   - `with session.begin(): process_one_attachment(...)`
2. Keep FTS rebuild outside attachment transaction, or make indexing per-attachment.
3. Avoid deleting old good extraction rows until the new parse/extraction result is ready, or write a new extraction run and mark prior rows superseded.

Acceptance tests:
- Force an exception after page parsing but before fact persistence; prior committed attachment remains intact.
- Reprocessing a failed attachment does not leave duplicate table cells.
- A failed attachment does not cause all prior attachments in the run to roll back.

### PY3 — Use Pydantic strict validation for extracted fact contracts

Current risk:
- `EvidenceFact` accepts loose coercion by default.
- Dates are strings on DTOs but SQLAlchemy columns are dates.
- Enum-like fields such as role/supersession/table kind are strings.

Why this matters:
- Pydantic v2 strict mode exists to avoid accidental type coercion. In this pipeline, accidental coercion can turn malformed numeric/date/factor data into plausible-looking facts.

Action:
1. Add strict Pydantic models for extraction outputs:
   - `EvidenceFact`
   - `TableCandidate`
   - `TableCellCandidate`
2. Use `Literal` or Python enums for:
   - `role`
   - `unit`
   - `supersession_status`
   - `table_kind`
   - `extraction_method`
3. Store numeric normalized values as both:
   - `normalized_value_text`
   - typed fields where applicable: `value_decimal`, `value_date`, `value_int`

Acceptance tests:
- `EvidenceFact(confidence="0.78")` fails in strict mode.
- Invalid role such as `"chosen"` fails.
- A malformed date fails before persistence.

### PY4 — Add Ruff and mypy before the codebase grows

Current risk:
- The project has no lint/type gates.
- The code is mostly typed, but several dynamic dict/JSON paths and optional fields can hide `None` errors.
- Imports from untracked modules can pass locally and fail elsewhere.

Action:
1. Add dev dependencies:
   - `ruff`
   - `mypy`
   - `types-PyYAML` if YAML tests remain.
2. Add `pyproject.toml` config:
   - Ruff: `E`, `F`, `I`, `UP`, `B`, `SIM`, `RET`, `RUF`
   - mypy: start moderate, then tighten
3. Add commands:
   - `ruff check .`
   - `ruff format --check .`
   - `mypy serff_intel`

Acceptance tests / CI gates:
- CI fails on unused imports, missing modules, and obvious bugbear warnings.
- mypy catches passing `str | None` where `str` is required in normalizer functions.
- No untracked source module is required for tests to pass.

### PY5 — Testing should isolate env/filesystem dependencies

Current risk:
- Some workflow tests depend on local extracted SERFF runs in `/private/tmp`.
- Environment variables such as `SERFF_INTEL_DB_URL` and `SERFF_INTEL_PROCESSED_DIR` can leak across test runs if not controlled.

Why this matters:
- pytest recommends `tmp_path` for unique per-test filesystem state and `monkeypatch` for environment/config mutation that is automatically undone.

Action:
1. Move reusable test setup into fixtures:
   - `settings_factory(tmp_path)`
   - `session_factory_for_test(tmp_path)`
   - `sample_comp_search_payload(tmp_path)`
2. Use `monkeypatch.setenv` for env-based CLI/config tests.
3. Never require `/private/tmp/serff-*` files for unit tests; mark real downloaded SERFF sample tests as integration tests.

Acceptance tests:
- `pytest -q` passes on a clean machine without `/private/tmp/serff-scan-demo-runs`.
- A CLI config test uses `monkeypatch.setenv` and proves the env is restored.
- Integration tests are skipped unless `SERFF_INTEL_INTEGRATION=1`.

### PY6 — Logging should replace print-style operational visibility

Current risk:
- CLI prints summary lines, but the pipeline has no structured logging.
- Long S3 runs will need progress, per-stage timing, warning counts, and failure summaries.

Action:
1. Add module loggers:
   - `serff_intel.pipeline`
   - `serff_intel.ingest`
   - `serff_intel.extract`
2. Add CLI `--log-level`.
3. Log per attachment:
   - filing ID
   - attachment ID
   - parser
   - pages
   - fact count
   - table count
   - errors
   - elapsed time

Acceptance tests:
- `caplog` verifies parse failures produce warning/error logs.
- CLI `--log-level DEBUG` enables debug logs.
- Summary log reports counts that match DB counts.

### PY7 — Avoid mutable hidden global state in extractors

Current risk:
- Extractors use module-level regex lists and maps. That is okay if immutable, but tests or future agents may mutate them.
- LLM-generated code often appends to globals in tests or runtime without realizing cross-test bleed.

Action:
1. Treat module constants as immutable:
   - tuples instead of lists where possible.
   - `MappingProxyType` or frozen dataclasses for fact maps if mutation becomes an issue.
2. Add tests that call extractors multiple times and ensure output does not grow or change.

Acceptance tests:
- Two consecutive calls to `extract_rate_facts` with the same input return identical facts.
- Tests do not monkeypatch global regex lists except inside a controlled context.

### PY8 — Add property/regression tests for numeric parsing

Current risk:
- Regexes are brittle around commas, dollars, parenthetical negatives, percent spacing, and multiple numbers near one label.

Action:
1. Add parametrized tests for numeric normalizer:
   - `12.4%`
   - `-5.0%`
   - `(5.0%)`
   - `$1,234,567`
   - `1.901`
2. Add regression tests for "distractor number before target number":
   - `"credibility 60%; selected rate level change 12.4%"`
   - `"Line 5 rounded LCM 2.002; prior LCM 1.901"`
3. Consider Hypothesis later for numeric token fuzzing, but do not add until deterministic fixtures are solid.

Acceptance tests:
- Parenthetical decreases normalize to negative decimal strings.
- Extractors select the value attached to the correct label, not the nearest unrelated number.
- Money and percentage normalization are distinct.

### PY9 — CLI should expose operational safety controls

Current risk:
- `process-pending` processes all pending/failed attachments.
- There is no dry run, limit, filing filter, or fail-fast mode.

Action:
1. Add:
   - `process-pending --limit N`
   - `process-pending --serff SERFF_ID`
   - `process-pending --fail-fast`
   - `process-pending --dry-run`
2. Add `summary --errors` after `processing_error` exists.

Acceptance tests:
- `--limit 1` processes exactly one attachment.
- `--serff X` does not touch filings outside X.
- `--dry-run` reports candidates but creates no pages/facts/tables.

### PY10 — Distinguish unit tests, smoke tests, and integration tests

Current risk:
- The repo currently has tests, but no clear test taxonomy.
- It is easy for an agent to add a test that depends on downloaded private files and accidentally make CI flaky.

Action:
1. Add pytest markers:
   - `unit`
   - `smoke`
   - `integration`
2. Make default `pytest -q` run unit/smoke only.
3. Put real SERFF downloaded sample runs behind an opt-in marker/env variable.

Acceptance tests:
- Running default tests does not require network, S3, or local downloaded PDFs.
- Running integration tests without env prints a skip reason.

---

## 9. Highly actionable improvement backlog

### Immediate patch set A — make current facts trustworthy

1. Persist `fact_key` into `ExtractedFact`.
2. Export `fact_key`.
3. Sort review CSV by `needs_review DESC`, `confidence ASC`.
4. Add `review_reason`.
5. Add parenthetical negative parsing.
6. Add `written_premium_impact` to exports.
7. Compute `requested_approved_rate_gap` when both sides exist.

Done when:
- `pytest -q` passes.
- New DB-level test proves high-value stored facts have catalogue keys.
- Review export top rows are review-required.
- A fixture with `(5.0%)` produces `-5.0`.

### Immediate patch set B — make failures recoverable

1. Add `processing_error`.
2. Add per-stage exception boundaries.
3. Add per-attachment transaction scope.
4. Add `process-pending --limit`.

Done when:
- A forced extractor exception records an error and continues.
- Failed attachment can be retried cleanly.
- Batch can be run safely on a 10-attachment subset.

### Immediate patch set C — stop catalogue overclaiming

1. Mark missing/deferred fact groups explicitly.
2. Demote keyword-only numeric facts or build numeric extractors.
3. Split statuses:
   - `sourced_from_metadata`
   - `extracted_numeric`
   - `keyword_only`
   - `table_candidate_only`
   - `deferred`

Done when:
- Catalogue status values are controlled.
- Every `partial` fact has a test fixture.
- No keyword-only fact is described as a reliable numeric fact.

### Immediate patch set D — table reliability

1. Add parser source to `ExtractedTable`.
2. Use Excel/DOCX structured tables before line heuristics.
3. Link promoted facts to `table_cell_id`.
4. Keep raw cells separate from analytical facts.

Done when:
- Excel fixture creates cells with parser source `excel_sheet`.
- High-confidence table-derived LCM/profit fact has `table_cell_id`.
- Low-confidence cells remain QA-only.

### Immediate patch set E — code quality gates

1. Add Ruff.
2. Add mypy.
3. Add pytest markers.
4. Add CI command block to README.

Done when:
- `ruff check .` passes.
- `mypy serff_intel` passes or has a documented baseline.
- `pytest -q` default is deterministic and local-only.
