# Table-Extraction Frontier — validated spec for the next milestone

**Date:** 2026-06-28
**Source:** 8-analyst discovery pass over the real Accredited Surety / Brazos filing (`data/processed/text`), values validated against source. Scoreboard: `scripts/score_extraction.py`.

## Where the improve-loop landed

Prose + **labeled-scalar** facts are now captured. Golden scoreboard: **overall recall 26/26 (100%), false-positive guards 5/5, review rate 22%, 64 tests green.** Iterations shipped: trucking-heading FP, coverage×LCM matrix, Exhibit C statewide change, identical-percent de-noising, Selected A-Priori → expected_loss_ratio, Risk Load → risk_load.

A `labeled_scalar` fact is a label and one value on a line (`Selected A-Priori 90.9%`, `Risk Load 5.3%`). A simple label→value regex nails these. **They are done.**

## What remains — and why regex is the wrong tool for it

Discovery classified **53 remaining high-value targets** as `labeled_series` (29) or `grid_cell` (24). These are *not* missing-because-no-pattern; they're missing because the value's meaning depends on table structure. Proof it's not a regex gap: the current extractor already mis-reads `Permissible Loss & LAE Ratio = 100% - (9) 58.1%` as **100** (first %), not 58.1. **On grid/formula text, more regexes produce wrong values, not missing ones — strictly worse.**

### Category A — Experience loss ratios & premiums (grid_cell, ~15 targets)
`attachment_2/3`: rows like `2024 21,482,380 19,377,950 8,739,868 12,845,497 66.3%`. The 66.3% is the incurred loss & DCCE ratio for (year=2024, geography=Texas). Per-cell value needs the year (row), the column identity (B/C/D/E), and the table title (Texas vs Countrywide).
- **Needs:** a year-row + column-classified extractor, and **new catalogue keys** (`experience_loss_ratio`, `earned_premium`, `incurred_loss`) carrying `effective/experience period` + `coverage` + `scope=territory|countrywide`.

### Category B — On-level factors & per-year rate changes (labeled_series, ~10 targets)
`attachment_12`: `On-Level Factor 1.524 1.510 1.414 1.387 1.302 1.208 1.000` and per-year rate changes `0.9% 6.8% 1.9% 6.6% 7.8%`. One label, N year-columns; the actuary wants a specific column (current/prospective/selected).
- **Needs:** a label→series extractor that emits one fact **per year** with the year dimension, not a collapsed scalar. `on_level_factor` already carries `[coverage, experience_period]`; populate that dimension.

### Category C — LDF / CDF triangles (grid_cell + series, ~20 targets)
`attachment_13/14`: `Age 3 → 9.66 (Incurred CDF) / 20.66 (SOLM CDF) / 60.86 (Paid CDF) / 625.38 (Data Paid CDF)`. Each cell is (coverage, maturity/age, paid-vs-incurred, basis). The column header is shattered across multiple lines.
- **Needs:** genuine multi-line **header reconstruction** + cell→fact promotion. `loss_development_factor` / `cumulative_loss_development_factor` already carry `[coverage, maturity]`; populate them.

## The milestone (CH6 / Tier-3 — "make table extraction honest")

1. **Pre-clean PDF artifacts before tabling** (`tables.py`): glue `"1 ,772,633"`→`"1,772,633"`, join `"$ 8 ,234"`, drop standalone chart-axis tokens (`$9,000`), drop notes/prose lines. (Fixes the corruption the audit found: 33 intra-number splits, 16 `$`-splits, 10 phantom cells.)
2. **Capture multi-line headers** and classify columns (premium/loss/ratio/CDF/on-level/year).
3. **Promote high-confidence cells to typed facts** with `table_cell_id` provenance, the row label as dimension (year/age/coverage), and the column identity as fact_type.
4. **Add the catalogue keys** the experience/premium facts need (`experience_loss_ratio`, `earned_premium`, `incurred_loss`, `large_loss_load`, `total_lae_ratio`).
5. **Gate by confidence:** promote a cell to an analytical fact only when header+structure are trustworthy; otherwise keep it as a review-flagged table cell (never a silent wrong scalar).

**Acceptance:** the golden set grows to include the Category A/B/C anchors (already validated and inventoried above), and `scripts/score_extraction.py` measures table-borne recall on them — same loop, harder anchors.

## Bottom line
The labeled-scalar facts are nailed (26/26). The remaining 53 are a **structured table-reconstruction problem**, fully specified above with validated values. It is its own milestone, not another regex — and doing it as a regex would regress accuracy (the 100% example). The validated target inventory in this doc is the spec to build it against.
