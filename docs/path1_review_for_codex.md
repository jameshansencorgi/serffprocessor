# Path 1 (Claude) → Codex Review Request

**What this is.** Claude completed a slice of Path 1 (extraction correctness + catalogue contract). This document asks Codex to review it, and lists exactly what Codex must wire/verify on the Path 2 side. Suite is green: `.venv/bin/pytest -q` → **28 passed**. Nothing is committed.

**Files Claude changed (Path 1 only):** `serff_intel/extract/{schemas,rate_impact,objections,entities,fact_keys,enums}.py`, `tests/test_catalogue_reconciliation.py`. Claude did **not** touch `models.py`, `pipeline.py`, `cli.py`, `services.py`, `storage/`, `ingest/`, or `tables.py`.

---

## 1. What Claude shipped

### 1.1 Canonical `fact_key` (C1)
- `serff_intel/extract/fact_keys.py`: `CANONICAL_FACT_KEY: dict[str,str]` + `canonical_fact_key(fact_type) -> str|None`. Maps extractor `fact_type` → `fact_catalogue.yml` key (e.g. `requested_rate_change → requested_overall_rate_change`).
- `EvidenceFact.fact_key` is set by the extractors.
- Conformance test: every mapped value exists as a catalogue key.

### 1.2 Shared controlled vocab (CH10)
- `serff_intel/extract/enums.py`: `ROLES`, `UNITS`, `SUPERSESSION_STATUSES`, `TABLE_KINDS`, `EXTRACTION_METHODS`, `REVIEW_REASONS`, `OBJECTION_TOPICS`, `DISPOSITIONS` (all `frozenset`).
- **`REVIEW_REASONS` now includes `unknown_fact_key`** — Claude adopted the value Codex emits at `pipeline.py:148` into the shared vocab so it is no longer out-of-contract.

### 1.3 `review_reason` on facts (CH4/H2)
- `EvidenceFact.review_reason: str|None`. The rate extractor sets `ambiguous_role` (unknown role on a role-required fact) or `distractor_number` (see 1.4). All emitted values are in `REVIEW_REASONS`.

### 1.4 Distractor-aware numeric extraction (C2)
- `rate_impact.py` rewritten from inline-value regexes to **label-only patterns + `_select_percent_value()`**, which skips a percent whose preceding phrase is a distractor cue (`credibility`, `confidence`, `complement`, `weight`, …) and falls back to the first percent flagged `is_distractor=True`.
- Parenthetical decreases `(5.0%)` → `normalized_value="-5.0"`; explicit `-5.0%` preserved; `$1,234,567` → `1234567`.
- `written_premium_impact` split into its own helper (`_extract_written_premium_facts`).

### 1.5 H4 pure functions (for Codex to wire — P2.8)
- `objections.classify_objection_topic(text) -> str` → value in `OBJECTION_TOPICS`.
- `objections.split_objection_and_response(text) -> tuple[str, str|None]`.
- `entities.normalize_disposition(raw: str|None) -> str|None` → value in `DISPOSITIONS` or `None`.

---

## 2. What Codex must wire / verify (action items)

1. **Wire the objection split (P2.8).** `pipeline.py:192` still hardcodes `topic="general"` and never sets `company_response_text`. Replace with:
   - `topic=classify_objection_topic(fact.evidence_text)`
   - `objection_text, company_response_text = split_objection_and_response(fact.evidence_text)`
2. **Wire disposition normalization (P2.8).** Map `Filing.status` through `normalize_disposition(...)` on import (`ingest/*`), keeping the raw string when it returns `None`.
3. **Add a DB-level vocab guard (CH10).** A test that every persisted `ExtractedFact.review_reason` is in `REVIEW_REASONS`, every `role` in `ROLES`, every `unit` in `UNITS`. This is the enforcement that stops future drift like the `unknown_fact_key` case — please own it in `test_pipeline.py`/`conftest`.
4. **Confirm `fact_key` persistence still matches the map.** Claude's `canonical_fact_key` returns `None` for `expense_provision` (no catalogue aggregate key exists). Your fallback turns that into `fact_key="unknown"` + `needs_review=True`. Decide jointly whether to add an `expense_provision` aggregate key to the catalogue (Claude can do it on the catalogue side) or keep it review-routed.

---

## 3. Things to scrutinize in review (Claude's known limitations)

- **`_select_percent_value` window is 80 chars.** A value >80 chars from its label is dropped (miss, not mis-capture). Acceptable, but flag if real fixtures show longer gaps.
- **Distractor list is heuristic.** Only the named cues are skipped; a novel distractor noun would still be captured. The fallback flags `distractor_number` so it lands in review rather than silently.
- **LCM still uses `decimals[-1]`** (last decimal in window). Claude did **not** change `_extract_lcm_facts` in this pass — table-structured LCM grids are the better long-term path (deferred CH6/table work). Treat inline LCM values as review-grade.
- **Duplicate profit facts.** `"selected underwriting profit provision 9.0%"` matches both the `selected underwriting profit provision` label and the `profit provision` label → two facts (roles `selected` and `unknown`). Pre-existing behavior, preserved. Dedup is a future item.
- **`classify_objection_topic` is first-match-wins by cue order.** `trend` is checked before others, so "expense trend" → `trend`. Fine for triage; not a taxonomy.

---

## 4. Test coverage Claude added (`tests/test_catalogue_reconciliation.py`, 16 tests)
fact_key map ⊆ catalogue; extractor sets canonical key; parenthetical & explicit negatives; `$` formatting; distractor-between & distractor-before; roles ⊆ `ROLES`; review_reason ⊆ `REVIEW_REASONS`; `unknown_fact_key` declared; objection topic vocab; objection/response split (with and without response); disposition mapping ⊆ `DISPOSITIONS`.

**Not covered by Claude (please add on Path 2):** end-to-end persistence of `fact_key`/`review_reason` from a real `process_pending` run, and the vocab guard in item 2.3.
