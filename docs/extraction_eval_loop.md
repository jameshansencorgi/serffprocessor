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

| Run | Recall | Vocab accuracy | `key=none` | Hallucination | Notes |
| --- | ---: | ---: | ---: | ---: | --- |
| Regex pipeline | 60% | 100% | 0 | 0 | deterministic, free; weak on tables (grid 9%) |
| Haiku v1 (plain prompt) | 97% | 73% | 35 | 0 | strong recall, loose vocab |
| **Haiku v2 (key defs + few-shot)** | **100%** | **86%** | **4** | **0** | iteration 1 win |
| Opus v1 (plain prompt) | 100% | 76% | 199 | 22 | exhaustive but costly + drifts |

**Iteration 1 (Haiku v1 → v2)** added precise key definitions (distinguishing
`experience_loss_ratio` from `expected_loss_ratio`), the missing keys (`experience_loss_ratio`,
`earned_premium`, `incurred_loss`), and four worked examples targeting the observed failures
(the formula-line `= 100% - (9) 58.1%` trap, experience rows, coverage matrices). Effect:
recall 97→100%, vocab 73→86%, `none` drift 35→4, hallucination still 0.

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

## Next iterations (open levers)
1. Close the remaining 6 vocab misses (inspect which keys the scorer still rejects).
2. Add a cheap **verification pass** (a second Haiku call to refute each fact) for the few residual errors.
3. Promote the `experience_loss_ratio` / `earned_premium` / `incurred_loss` keys into the catalogue so these facts have a real home (currently scored via `key_aliases`).
4. Wire the Haiku pass + guards into the pipeline as a real extractor stage (needs API integration), cross-checked against the regex layer.
