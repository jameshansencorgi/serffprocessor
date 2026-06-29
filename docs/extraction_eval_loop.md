# Extraction Eval & Improve Loop (LLM extraction)

**Goal:** keep improving SERFF fact extraction with a measured loop. We can't fine-tune model
weights in this environment, so "train" here means **eval-driven prompt + post-processing
optimization**: a labeled test set, a scorer, and iterations we measure every time. The eval
set also seeds few-shot examples and a future fine-tune corpus.

## The loop

1. **Test set** — `tests/golden/extraction_eval.yml`: validated facts per doc (`key`, `value`,
   `coverage`, `bucket`), with `key_aliases` so we score *meaning* not exact strings.
2. **Run the model** — extract from raw source → a run JSON (`[{doc, facts:[{catalogue_key, value, ...}]}]`).
   The reusable Haiku run is a workflow (current best prompt below).
3. **Score** — `scripts/eval_extraction.py --facts run.json` reports recall by bucket, vocabulary
   accuracy, hallucination (value-in-source), and fact volume. `--regex` scores the regex pipeline.
4. **Diagnose** the weakest metric, **edit the prompt / post-processing**, re-run, compare delta.

## Results so far (10 real docs, 46-fact eval)

Two recall numbers: **loose** (value appears anywhere on the page — optimistic) and **strict**
(value + acceptable key, matched 1:1 so a single value can't satisfy two anchors — trustworthy).
Always quote strict.

| Run | loose recall | **strict recall** | vocab | contradictions | hallucination | gate |
| --- | ---: | ---: | ---: | ---: | ---: | :--: |
| Regex pipeline | 60% | **60%** | 100% | 1 | 0 | FAIL |
| Haiku v1 (plain) | 97% | **71%** | 73% | 2 | 0 | FAIL |
| Haiku v2 (key defs + few-shot) | 100% | **86%** | 86% | 0 | 0 | FAIL |
| Opus v1 (plain) | 100% | **76%** | 76% | 0 | 22 | FAIL |

**Iteration 1 (Haiku v1 → v2)** added precise key definitions, the missing keys, and four
worked examples. Real effect (strict): recall 71→86%, vocab 73→86%, **contradictions 2→0**,
hallucination 0. Best run (Haiku v2) is still **below the acceptance bar** — the loop is not "done".

`contradictions` = the run claimed an evaluated key with the WRONG value (regex: `permissible=100`
from `100% - (9) 58.1%`; Haiku v1: `requested=37.1`, the prior-year change, instead of `47.5`).
The old value-only scorer hid all of these.

## Acceptance criteria (enforced by `--gate`, non-zero exit on fail)

A run is acceptable only when **all** hold:
- strict recall ≥ 0.90
- vocab accuracy ≥ 0.90
- contradictions = 0 (no wrong values on evaluated slots)
- hallucination = 0 (every emitted value present verbatim in source)
- (regression) no metric below the last committed baseline

`.venv/bin/python scripts/eval_extraction.py --facts run.json --gate` → exit 0 pass / 1 fail.

## Critical review — what this loop does NOT yet prove (honest caveats)

1. **One filing.** All 46 anchors come from a single carrier (Accredited/Brazos). Results will not
   generalise to other SERFF formats until the eval spans multiple carriers/states.
2. **Truth provenance.** Eval values were partly produced by an LLM discovery pass and spot-checked
   against source, not fully hand-labelled. Some anchors may themselves be wrong.
3. **Train/test contamination — MEASURED.** The v2 few-shot examples are drawn from eval docs
   1/2/8/14, so the 86% was inflated. Splitting the eval (`heldout_docs` in the eval YAML) gives
   the honest picture: **Haiku v2 in-prompt 100% (23/23) vs held-out 73% (17/23)** — a 27-point gap
   confirming memorisation. Regex (a non-learning control) shows no gap (56% vs 69%). **Report
   held-out recall as the real number, and judge future prompt iterations on it.** Open: few-shot
   examples should come from OUTSIDE the eval set so the whole eval is held out.
4. **n = 1, non-deterministic.** Each model was run once; LLM output varies. The deltas are point
   estimates with no variance. **Gate should require K-run stability (e.g. min over 3 runs).**
5. **Coverage/scope/role under-scored.** Strict recall checks value+key; coverage accuracy is reported
   but not gated (regex sets coverage on only 2/28 matches). role/scope/unit are not evaluated at all.
6. ~~**Not reproducible off this machine.**~~ ADDRESSED: the 10 eval docs are committed under
   `tests/golden/fixtures/`; the scorer and tests fall back to them when `data/processed/` is absent,
   and a deterministic `test_regex_pipeline_gate_no_contradictions_and_recall_floor` now gates the
   regex path in CI (contradictions = 0, strict recall ≥ floor).
7. **Recall, not precision, on volume.** A model emitting many extra facts isn't penalised beyond the
   hallucination/none counts; there is no full-precision measure against an exhaustive label set.

## Current best prompt (Haiku v2 — iterate on this)

Rules: report every high-value value with its EXACT source token; be exhaustive on table rows;
copy the `source_line` (provenance); map coverage Liability→AL, Physical Damage→APD, BI→BI, PD→PD.

Key meanings (where models go wrong):
- `experience_loss_ratio`: a HISTORICAL loss/LAE ratio for a specific PAST year (Exhibit D).
- `expected_loss_ratio`: the PROSPECTIVE expected/permissible ratio used in the indication (incl. a-priori).
- `permissible_loss_ratio`: 100% − total expense & profit.
- `requested_overall` / `indicated` / `selected` rate change; `on_level_factor`; `loss_development_factor`
  (age-to-age) vs `cumulative_loss_development_factor` (to-ultimate); `earned_premium` / `incurred_loss`.

Worked examples:
- `2024 … 12,845,497 66.3%` in a Texas experience table → `experience_loss_ratio 66.3% (AL)` — NOT expected.
- `Permissible Loss & LAE Ratio = 100% - (9) 58.1%` → `permissible_loss_ratio 58.1%` — take the result, not 100.
- `Liability 2.002` under `Coverage LCM` → `loss_cost_multiplier 2.002 (AL)`.
- `Selected A-Priori 90.9%` → `expected_loss_ratio 90.9%`.

## Post-processing (always applied to LLM output)
- **Value-in-source guard:** drop/flag any fact whose value isn't present verbatim in the source (auto hallucination filter; the scorer measures it).
- **Key normalization:** map to catalogue keys; route `none` to the review queue.
- **Regex cross-validation:** where the regex pipeline and the LLM agree on a value → high confidence; where they disagree (e.g. regex `100` vs LLM `58.1` on the permissible formula line) → flag for review.

## Next iterations (open levers — prioritised by the critical review)
1. **Rigour first (or the numbers don't mean anything):** add a held-out doc split (kill train/test
   contamination), make `--gate` require K-run stability (min over ≥3 runs), and commit a tiny
   redacted fixture corpus so the eval is reproducible/CI-able.
2. **Close Haiku v2 to the bar:** strict recall 86→≥90 and vocab 86→≥90 — inspect the 6 vocab misses
   and the labeled_series strict gap (7/13: values found but mislabelled/duplicated on series rows).
3. Add a cheap **verification pass** (second Haiku call to refute each fact) for residual contradictions.
4. Promote `experience_loss_ratio` / `earned_premium` / `incurred_loss` into the catalogue (currently via `key_aliases`).
5. Broaden the eval to multiple carriers/states before trusting any generalisation claim.
6. Wire the Haiku pass + guards into the pipeline as a real extractor stage, cross-checked against the regex layer.
