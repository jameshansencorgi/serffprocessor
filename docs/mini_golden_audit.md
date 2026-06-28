# Mini Golden Audit

Date: 2026-06-28

Purpose: quick, partial version of the golden SERFF testing plan to estimate how far the current prototype is from useful MVP-level extraction. This is not a full labelled corpus; it is a representative smoke audit over 11 real processed attachments from `data/processed/text`.

## Sample

Documents checked:

- `attachment_1`: exception / LCM page
- `attachment_4`: expense exhibit
- `attachment_6`: profit exhibit
- `attachment_8`: rate indication
- `attachment_10`: LCM / expense exhibit
- `attachment_14`: trend exhibit
- `attachment_15`: trend exhibit
- `attachment_16`: checklist / administrative context
- `attachment_18`: rate indication
- `attachment_23`: authorization letter
- `attachment_24`: exception / LCM page

Fact anchors checked: 19 high-value expected facts from the prior extraction audit.

## Results

| Metric | Result | Interpretation |
| --- | ---: | --- |
| Document categorisation accuracy | 7 / 11 = 63.6% | Too low for automated routing. |
| High-value fact anchor recall | 16 / 19 = 84.2% | Much improved for selected prose/semi-structured facts. |
| Matched facts not needing review | 9 / 16 = 56.2% | Still too many extracted facts require review. |
| Matched facts needing review | 7 / 16 = 43.8% | Review policy is conservative; good for safety, bad for analyst burden. |
| Overall extracted fact review rate | 16 / 51 = 31.4% | Better than "everything needs review," but still high. |
| Mini false-positive checks failed | 2 | `trucking` still fires on exception pages with commercial-auto/truckers headings. |

## Rough Completion Estimate

Against the MVP goal of "categorise correctly, extract relevant facts, and avoid unnecessary manual review":

- Document categorisation: **~64% complete**
- Prose/semi-structured fact extraction: **~84% complete on this mini anchor set**
- Review burden reduction: **~56% complete**
- False-positive cleanup: **~80% complete on the mini checks, but still has important leakage**
- Table-heavy extraction: **not measured here; prior audit suggests still low**

Overall MVP readiness estimate from this mini audit: **~65-70% of the way there for headline/prose extraction, but materially lower for table-heavy actuarial reconstruction.**

## Main Failures

### Classification misses

- `attachment_8`: expected `rate_indication`, got `experience_exhibit`
- `attachment_10`: expected `lcm_exhibit`, got `expense_exhibit`
- `attachment_16`: expected administrative/checklist context, got `rate_indication`
- `attachment_23`: expected `authorization_letter`, got `filing_summary`

### Fact misses

- `attachment_1`: missed `loss_cost_multiplier = 2.002`
- `attachment_18`: missed `requested_rate_change = 47.5`
- `attachment_24`: missed `loss_cost_multiplier = 2.002`

### Review burden

Correctly matched but review-flagged facts include:

- expense ratios from `attachment_4` flagged as `ambiguous_percent_candidates`
- `loss_cost_multiplier = 2.002` in `attachment_10` flagged as `ambiguous_role`
- frequency/severity trends in `attachment_14` flagged as `ambiguous_percent_candidates`

### False positives

- `trucking` still appears in `attachment_1`
- `trucking` still appears in `attachment_24`

This is no longer the old broad `commercial auto` bug, but there is still leakage from exception-page wording. These should likely be treated as document/topic context, not actuarial narrative-driver facts.

## Recommended Next Fixes

1. Improve document-class precedence.
   - Prefer filename/exhibit identifiers and stronger class-specific cues over generic `loss ratio`, `approved`, or `serff tracking` terms.
   - Add negative/administrative cues for checklist and authorization letters.

2. Add table-row LCM extraction for exception pages.
   - Specifically recover coverage / LCM matrices from `attachment_1` and `attachment_24`.

3. Reduce unnecessary review for clean labelled expense/trend rows.
   - If label and value are on the same row and the row has one plausible percent, do not mark `ambiguous_percent_candidates`.
   - If multiple percents appear because the extractor scan crosses table columns, use row-aware extraction instead of a free 80-character scan.

4. Reclassify `trucking` as contextual unless it appears in a narrative rationale sentence.
   - Avoid emitting it from headings/manual titles alone.

5. Promote this mini audit into a real test fixture.
   - Store expected classes and expected fact anchors in YAML.
   - Add a pytest that fails on regression and reports precision/recall/review rate.
