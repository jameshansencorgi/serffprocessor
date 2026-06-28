# SERFF Fact Catalogue

This catalogue defines the facts the SERFF processor should extract from filings and how useful each fact is for actuarial analysis. The current pipeline stores all extracted values in `extracted_fact` as evidence-backed observations. The catalogue is the bridge from those observations to a relational actuarial model.

## Fact Tiers

| Tier | Meaning | Treatment |
| --- | --- | --- |
| 0 | Filing spine metadata | Required for every filing and used for joins, dedupe, time series, and filtering. |
| 1 | High-value actuarial numeric facts | Core actuarial facts that should become normalized analytical tables. |
| 2 | Rating plan facts | Rates, factors, fees, caps, floors, and formulas needed to reconstruct premium. |
| 3 | Structured table facts | Cell-level facts from exhibits where row/column labels carry meaning. |
| 4 | Rules, context, and regulator interaction | Searchable and useful for explanation, review, and compliance; lower priority for first actuarial MVP unless numeric values are present. |

## Cross-Cutting Fields

Every fact should carry these attributes, whether it lands in a narrow analytical table or remains in the generic evidence table:

| Field | Purpose |
| --- | --- |
| `fact_key` | Stable canonical name from `fact_catalogue.yml`. |
| `filing_id` | Link to the normalized filing. |
| `attachment_id` | Source document. |
| `page_number` | Source page when available. |
| `table_locator` | Table name/number, row label, column label, or approximate locator. |
| `evidence_text` | Short human-reviewable support text. |
| `raw_value` | Value exactly as extracted. |
| `normalized_value` | Typed/cleaned value for analysis. |
| `unit` | Percent, dollars, count, factor, text, date, code, or composite. |
| `coverage` | Coverage/peril when applicable, such as AL, APD, BI, PD, homeowners peril. |
| `scope` | Overall, coverage, territory, tier, class, factor level, policy, renewal, new business. |
| `territory` | Territory code/name if applicable. |
| `effective_date` | Date the value applies. |
| `prior_filing_id` | Filing superseded by this fact when known. |
| `confidence` | Extraction confidence. |
| `needs_review` | True when confidence/context is insufficient for automated analytical use. |
| `extraction_method` | Regex, table parser, filename inference, LLM review, manual review, etc. |

## Current MVP Extraction

The current prototype already extracts these fact families:

| Fact family | Current status | Importance |
| --- | --- | --- |
| Filing metadata | Partially normalized from comp-search/manual metadata and text backfill. | Critical |
| Overall requested/approved/selected rate changes | Partial. Overall rate change is found in Exhibit G-like text. Approved/requested gap is not yet canonical. | Critical |
| Loss cost multipliers | Partial. Extracted, but duplicates and indicated/selected/prior labels need normalization. | Critical |
| Profit provisions | Partial. Extracted, but indicated vs selected needs canonical role labeling. | High |
| Expense provisions | Weak. Some expense text is present, but components are not yet structured. | High |
| Trend/credibility/reason tags | Weak. Keyword tags exist; numeric trend and credibility values are not reliably extracted. | High |
| Regulator objections | Basic snippets only. | Medium |
| Segment/document routing metadata | Strong enough for MVP QA. | Medium |

## Missing From First Test Runs

The first real SERFF test filing showed these important gaps:

1. Coverage normalization.
   AL/APD was visible in filenames and exhibit names, but facts did not consistently carry `coverage`.

2. Fact role normalization.
   The processor extracted values like `2.002`, `1.901`, `18.4`, and `9.0`, but did not reliably label them as indicated, selected, prior, rounded, or offset.

3. Table extraction.
   Many high-value PDFs were table-heavy. Regex snippets captured some values, but not row/column labels or table structure.

4. Expense components.
   Commission, other acquisition, general expense, taxes/licenses/fees, total expense/profit, permissible loss ratio, and risk load were visible but not consistently structured.

5. Ratemaking inputs.
   LDFs, frequency/severity trends, credibility, experience period, on-level factors, and selected assumptions need dedicated extractors.

6. Rate impact distribution.
   Policyholder count, dollar impact, min/max impact, and impact bands were not extracted.

7. Rating plan reconstruction.
   Base rates, loss costs, rating factors, rating variables, formula sequence, caps/floors, and rounding rules are not yet extracted.

8. SERFF source metadata.
   Filing source fields such as product name, TOI code, state status, and QA status, plus attachment fields such as section, form name, form number, submitted date, and download URL should be normalized.

## What Is Not Necessary For The First Actuarial MVP

These are useful but should not block the MVP:

- Full policy form/endorsement parsing unless the form changes rate applicability.
- Broad underwriting eligibility rule extraction unless a rule changes tier, surcharge, decline, or referral logic.
- Complete formula replay for every filing before table extraction is reliable.
- Narrative tags as analytical features unless tied to a numeric assumption or regulator objection.
- Perfect territory remapping before we can at least preserve territory codes and table labels.

## Recommended Relational Destinations

| Destination table | Facts |
| --- | --- |
| `filing` / `filing_source_metadata` | Filing spine and SERFF-native filing metadata. |
| `attachment` / `attachment_source_metadata` | Attachment catalogue and SERFF-native attachment metadata. |
| `rate_change_fact` | Overall/by-coverage/by-territory rate changes and impact distribution. |
| `loss_cost_or_base_rate_fact` | Base rates, loss costs, LCMs, exposure bases. |
| `rating_factor_fact` | Rating variables, levels/bands, factors, factor type, algorithm position. |
| `rating_algorithm_step` | Formula text, ordered operations, operands, worked examples. |
| `cap_floor_rounding_rule` | Caps, floors, minimum premiums, maximum premiums, rounding rules. |
| `fee_expense_profit_fact` | Fees, expense components, profit, contingency, permissible/expected loss ratios. |
| `actuarial_assumption_fact` | Trend, LDF, credibility, on-level, catastrophe, reinsurance, experience period. |
| `territory_definition` | Territory code definitions and remaps. |
| `regulatory_interaction` | Objections, responses, topics, resolutions. |
| `extracted_fact` | Immutable evidence log and fallback for facts not yet normalized. |
