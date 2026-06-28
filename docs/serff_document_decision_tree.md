# SERFF Document Decision Tree

This prototype treats every SERFF attachment as evidence, but it does not treat every attachment as equally useful. The pipeline saves the raw attachment, extracted text, pages, chunks, and an auditable parse decision for each document.

## Parse Routing

1. Identify file type.
   - `.pdf`: try native text extraction first.
   - `.docx`: extract paragraphs and tables.
   - `.xlsx`/`.xlsm`/`.csv`: route as structured spreadsheet evidence.
   - Other text-like files: store available text and queue unusual types for review.

2. Classify document purpose.
   - High-value actuarial: actuarial memo, rate indication, exception page, rate manual, LCM exhibit, trend exhibit, LDF exhibit, experience exhibit, expense exhibit, profit/ROE exhibit.
   - Useful context: objection letters, company responses, filing summary, rule manual, form schedule, ISO circular/adoption list.
   - Store-only/provenance: authorization letters, approval letters, administrative cover material.
   - Review queue: unknown or weakly classified documents.

3. Decide extraction route.
   - `native_text`: text-rich PDF or document; run direct extraction.
   - `native_text_table_aware`: text-rich and numeric/table-like; preserve page/table context for actuarial extraction.
   - `native_text_weak_review`: sparse native text; use what we have and flag high-value documents for OCR/layout review.
   - `ocr_required`: near-empty PDF text; likely scanned image.
   - `spreadsheet_structured`: parse workbook sheets/ranges.
   - `native_text_store_only`: extract and save for provenance, but do not treat as primary actuarial support.

## Concrete Extractables By Document Class

| Document class | MVP extractables | Primary use |
| --- | --- | --- |
| `actuarial_memo` | requested/selected/indicated rate change, actuarial rationale, credibility method, trend assumptions, expense/profit provisions, LCM references | Filing-level actuarial summary and model features |
| `rate_indication` | indicated vs selected rate changes, permissible loss ratio, projected loss ratio, credibility, on-level factors | Compare company indication to approved/requested action |
| `exception_page` | loss cost multiplier, base rates, minimum premiums, class/territory exceptions, schedule rating factors | Current rating algorithm and manual delta tracking |
| `rate_manual` | rates, factors, territories, symbols/classes, minimum premiums, rating rules | Rating database and pricing reconstruction |
| `lcm_exhibit` | loss cost multiplier, expense constant, variable expense, profit load, expected/permissible loss ratio | Carrier expense/profit assumptions and ISO loss cost deviations |
| `trend_exhibit` | frequency trend, severity trend, loss trend, selected vs indicated trend, trend period | Rate need decomposition and assumption benchmarking |
| `ldf_exhibit` | loss development factors, selected age-to-age factors, cumulative development, accident/report year support | Reserve/rate adequacy diagnostics |
| `experience_exhibit` | earned premium, written premium, incurred losses, claim counts, loss ratios, exposure counts by year/coverage | Experience analysis and competitor benchmarks |
| `expense_exhibit` | commission, other acquisition, general expense, taxes/licenses/fees, fixed/variable split, LAE | Expense provision benchmarking |
| `profit_exhibit` | underwriting profit provision, ROE, investment income offset, target surplus, risk load | Profit/risk load comparison |
| `objection_letter` | objection topic, requested support, actuarial/regulatory concern, due dates, unresolved questions | Regulator friction and issue taxonomy |
| `company_response` | response text, revised assumptions, supplied support, concession/resolution status | Track model changes caused by objections |
| `iso_reference_list` | adopted ISO circulars, loss cost effective dates, rule circular identifiers | External rate/rule provenance |
| `filing_summary` | tracking number, company, state, line, filing type, dates, status, disposition | Corpus indexing and deduplication |
| `authorization_letter` / `approval_letter` | company/legal authority, approval/disposition status, dates | Provenance and compliance context |

## MVP Acceptance Criteria

- Each attachment has exactly one parse decision after `process-pending`.
- `attachments.csv` includes route, value tier, OCR need, native text character count, table-like score, and route reason.
- High-value documents with sparse text are visible in exports as OCR/review candidates.
- Administrative documents are still saved and searchable, but tagged `store_only`.
- Unknown documents remain in `review_queue` instead of disappearing from the corpus.
