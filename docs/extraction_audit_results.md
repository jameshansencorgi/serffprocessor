# Extraction Correctness Audit — Real SERFF Filing

**Date:** 2026-06-28
**Corpus:** Accredited Surety & Casualty / "Brazos" Texas Commercial Auto filing — the 24 extracted documents in `data/processed/text/attachment_*.txt`.
**Method:** Ran the live `extract_table_candidates` + `extract_rate_facts` + reason/objection extractors over every doc; one independent judge per document compared extraction to source (`/tmp/serff_audit/attachment_N.md` has the raw side-by-side).

## Headline

On real, table-heavy actuarial exhibits the system is **failing more than it's passing.** Of 19 docs with extractable content (5 are pure forms/letters, N/A):

- **Grades:** A:1, B:1, C:5, D:5, **F:7** → 12/19 (63%) are D or F.
- **Tables:** of 16 docs with a real table, **0 are clean**; 7 partial, 7 broken, 2 missed. Not one analytically-usable table was produced.
- **197 high-value facts missed**, **33 false positives** (18 of them the same `trucking`="commercial auto" bug).

The prose-fact extractors are roughly MVP-OK for **clean, single-value, fully-spelled labels** (e.g. "Overall Rate Change 47.5%", "Frequency Trend 3.6%"). They fail on (a) **abbreviated labels** and (b) **anything living in a real multi-column financial table** — which is where most actuarial value lives.

## Per-document scorecard

| Doc | Type | Grade | Tables | One-line verdict |
| --- | --- | --- | --- | --- |
| attachment_1 | ISO exception/LCM rules page | **F** | missed | Both LCMs 2.002 (Liability + Phys Dam) in a Coverage/LCM table — missed; only fact is a false-positive "TRUCKERS" heading grab |
| attachment_2 | Exhibit D historical experience (TX/CW) | C | partial | Table cells correct & loss ratios reconcile, but all headers + Texas/Countrywide labels lost; 0 facts |
| attachment_3 | Exhibit D historical experience | B | partial | Both triangles' values correct/aligned; headers + geo labels lost |
| attachment_4 | PC367 Exhibit E expense info | **F** | partial | All 16 expense/profit/LAE provisions missed; `$`/digit-split tables |
| attachment_5 | PC367 Exhibit E (dup) | **F** | broken | ~15 expense/profit/permissible-loss provisions missed |
| attachment_6 | PC371 profit page | C | n/a | Indicated 18.4% / selected 9.0% profit provision correct; rest missed |
| attachment_7 | PC371 profit page (dup) | C | n/a | Headline profit values correct but duplicated |
| attachment_8 | Exhibit R1 rate indication | C | broken | profit 9.0%, LCM indicated 2.002 / selected 1.901 correct; bulk of indication missed |
| attachment_9 | Exhibit R1 (dup) | D | broken | LCM + profit load captured; nearly every other indication input missed |
| attachment_10 | Exhibit G LCM + expense/profit | D | n/a | 47.5% rate change + 2.002 LCM right; entire expense/profit/permissible-loss block missed |
| attachment_11 | Exhibit G LCM (dup) | C | n/a | 47.5% + three LCM roles captured (Line 4 role ambiguous) |
| attachment_12 | Rate & On-Leveling | D | partial | **0 facts**; prospective 20.8% + on-level factors all unextracted; `$`-split/phantom-axis tables |
| attachment_13 | Loss Development Triangles | D | partial | Triangles clean-ish but age-to-age headers shattered into phantom cells |
| attachment_14 | Trend & Onlevel | **F** | partial | Only freq 3.6% / sev 10.1% caught; **Indicated Rate Change 116.2% missed**, all loss ratios + LDFs missed |
| attachment_15 | Reported Frequency | **A** | partial | Both selected trends correct, no wrong facts — best in corpus |
| attachment_16/17 | PC420 checklist | N/A | n/a | No actuarial values — correctly nothing |
| attachment_18 | PC365 Exhibit C rate level | **F** | broken | 47.5% + all headline numbers missed; only a trucking false positive |
| attachment_19 | PC365 (dup) | **F** | broken | Clean source, ~nothing of value extracted |
| attachment_20 | Loss-cost adoption memo | N/A | n/a | Narrative; nothing to extract |
| attachment_21 | Trend & Onlevel (25k) | D | broken | 23 tables detected but largely corrupted |
| attachment_22 | Reference-adoption index | N/A | broken | Filing-number catalog; non-actuarial |
| attachment_23 | Authorization letter | N/A | n/a | No actuarial content |
| attachment_24 | ISO exception/LCM rules page | **F** | missed | LCMs + minimum premiums missed; one false-positive "truckers" |

## Systematic failure modes (with counts)

### False positives — 33 total
- **`trucking`="commercial auto": 18.** The trucking keyword matches "commercial auto", which appears in nearly every doc header → a junk fact on almost every page, and it mislabels the line of business. **One-line fix.**
- Duplicate `profit_provision` re-extraction (same value, role unknown) on R1/PC371.

### Missed facts — 197 total, by theme
| Theme | Missed | Why |
| --- | --- | --- |
| premium / exposure / power units | 35 | table-borne |
| expense components (commission/general/taxes) | 22 | abbreviated labels, table-borne |
| loss ratio (experience) | 16 | table-borne |
| indicated / rate change | 16 | incl. "Indicated Rate Change" (no "level") → regex miss |
| permissible / expected loss ratio | 15 | no extractor; abbreviated label |
| LCM | 13 | table-borne (Coverage/LCM matrix) |
| profit | 12 | abbreviated label ("Profit 9.0%") |
| LDF / development factors | 11 | table-borne |
| on-level factors | 7 | table-borne |

### Table issues
| Defect | Docs |
| --- | --- |
| lost/missing header row | 28 |
| intra-number space split (`"1 ,772,633"`) | 33 |
| `$` split into its own cell | 16 |
| phantom chart/axis cells (`$9,000`) | 10 |
| prose/notes misclassified as table | 9 |
| `kind=unknown` (unclassified) | 10 |

## Prioritized fix plan

**Tier 1 — cheap, high-value, extractor-only (Path 1 / my lane):**
1. Drop `"commercial auto"` from the trucking keyword (and require trucking/truckers/motor carrier) — removes 18 of 33 false positives.
2. Make `"level"` optional in `indicated`/`selected` rate-change patterns — recovers "Indicated Rate Change 116.2%" and similar.
3. Add abbreviated line-item extractors: `Profit N%`, `Commission & Brokerage N%`, `General Expense(s) N%`, `Taxes, Licenses & Fees N%`, `Other Acquisition N%`, `Permissible Loss & LAE Ratio N%`, `Expected Loss Ratio N%`, `Loss Cost Modification Factor N.NNN`. Recovers ~49 missed facts that follow a regular "label → %" shape.

**Tier 2 — table cleaning (pre-process before `tables.py`):**
4. Normalize PDF artifacts before tabling: join `"$ 8 ,234"` → `"8234"`/`"$8,234"`, glue `"1 ,772,633"` → `"1,772,633"`, strip standalone chart-axis tokens (`$9,000`), and don't treat note/prose lines as tables.

**Tier 3 — structured tables + cell→fact promotion (deferred CH6 / needs the table-reliability work):**
5. Capture multi-line headers and classify columns, then promote high-confidence cells (LCM-by-coverage, on-level factors, LDFs, loss ratios, premiums) into typed facts with `table_cell_id` provenance. This is where the bulk of the remaining 197 misses live.

**Reality check for the MVP:** Tiers 1–2 are days of work and materially raise the grades on the prose/semi-structured exhibits. Tier 3 (real table understanding) is the gating item for the genuinely table-heavy docs (Exhibit R1, Trend/Onlevel, LDF, experience) and should be scoped as its own milestone — it is the difference between "extracts the headline number" and "reconstructs the indication."
