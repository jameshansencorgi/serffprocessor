# LLM vs. Regex Extraction — empirical comparison

**Date:** 2026-06-28
**Method:** 10 real filing docs. One Claude agent per doc extracted facts from **raw source only** (no pipeline, no golden set). Scored both the LLM output and the regex pipeline against the validated truth set (golden anchors + discovery-validated values), bucketed by how the fact is laid out. Script: `/tmp/compare_llm_regex.py`.

## Recall vs. validated truth (86 facts)

| Layout bucket | truth | regex | LLM |
| --- | ---: | ---: | ---: |
| labeled_scalar (label + one value on a line) | 31 | 19 (61%) | 30 (97%) |
| labeled_series (label + N year/age columns) | 23 | **0** | 22 (96%) |
| grid_cell (value needs a separate column header) | 19 | **0** | 19 (100%) |
| already_extracted (regex target) | 13 | 13 (100%) | 13 (100%) |
| **TOTAL** | **86** | **32 (37%)** | **84 (97%)** |

Cleaner framing:
- On facts the **regex targets** (labeled_scalar + already_extracted = 44): regex **32/44 (73%)**, LLM 43/44.
- On the **table frontier** (series + grid = 42 — half the value): regex **0/42**, LLM **41/42**.

**The LLM does table reconstruction natively** — it read year-rows, on-level series, and LDF triangles that the regex pipeline gets *zero* of. That frontier (the deferred CH6/Tier-3 milestone) is, in practice, an LLM-shaped problem.

## LLM precision / hallucination

The LLM emitted **608 facts** across 10 docs; **23 were not found verbatim in source** — but on inspection **none are fabricated numbers**: they are derived date-ranges ("2020-2024", "2020-2025") and **thousands-scale notation** ("$21,482 (000)" for a value the IEE page states in thousands). So numeric hallucination in this sample ≈ **0** — a genuinely strong result.

The real LLM weaknesses are different:
1. **Vocabulary drift — 211/608 facts mapped to `catalogue_key='none'`.** The LLM reads everything (every minimum premium, every cell) but much of it has no controlled-vocabulary home, and some is **mis-typed**: it mapped *historical experience* loss ratios to `expected_loss_ratio` and experience premiums to `written_premium_impact`. Values right, **semantic type loose** — exactly what the controlled catalogue exists to prevent.
2. **Scale/notation ambiguity** — `"$21,482 (000)"` means 21,482,000; a downstream consumer must know the scale. The regex captures the literal source token.
3. **No calibrated provenance / determinism** — no page offset, no `needs_review`/`review_reason`, not reproducible run-to-run. Regex facts carry `evidence_text`, `page_number`, and a review reason.
4. **Cost / latency / volume** — 10 docs ≈ 225k tokens, ~77s. The whole corpus × every filing × re-runs is materially more expensive than instant, free regex, and 608 facts is a lot of low-value noise to triage (many are $15/$21 minimum premiums).

## Where regex still wins
- **Precision + controlled vocabulary**: every regex fact carries a real `fact_key`, role, coverage, unit, and a review reason. (Caveat: regex also produces *wrong* values on formula lines — e.g. `Permissible Loss & LAE Ratio = 100% - (9) 58.1%` → captured `100` — but those are review-flagged.)
- **Determinism, provenance, zero marginal cost, reproducibility** — required for an auditable filing database.

## Recommendation: hybrid, not either/or

| | Regex/deterministic | LLM |
| --- | --- | --- |
| Recall (overall) | 37% | **97%** |
| Recall (table frontier) | 0% | **98%** |
| Numeric hallucination | none | ~none (in sample) |
| Controlled vocabulary | **enforced** | drifts (211 'none', some mis-typed) |
| Provenance / determinism / cost | **strong / free** | weak / paid / non-deterministic |

1. **Use the LLM for the table frontier** (grid_cell + labeled_series) where regex is 0%. It is the pragmatic way to "nail" table reconstruction without a bespoke parser — it would lift overall recall ~37% → ~97%.
2. **Constrain the LLM** the way this test did and then some: force-map to catalogue keys (route `none` to review), require the **exact source token** (preserves scale/notation) **and the source line** (provenance), and run a deterministic **value-in-source check** (the value must appear in the text — auto-catches hallucination, which is what `/tmp/compare_llm_regex.py` already does).
3. **Keep deterministic regex** for high-frequency labeled_scalar facts (cheap, reproducible) **and as a cross-validator**: where regex and LLM agree → high confidence; where they disagree (e.g. the `100` vs `58.1` permissible bug) → flag. Regex catching the LLM and vice-versa is the strongest signal either produces alone.

**Bottom line:** the regex pipeline is the right precision/provenance backbone; the LLM is the right tool for the table-heavy frontier. The measured gap (37% → 97%) is large enough that the table-reconstruction milestone should be built as a **schema-constrained, source-validated LLM pass**, cross-checked by the regex layer — not as more regex.
