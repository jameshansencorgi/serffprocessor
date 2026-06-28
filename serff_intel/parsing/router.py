from __future__ import annotations

from dataclasses import dataclass
import re

from serff_intel.parsing.text_extract import PageText


HIGH_VALUE_CLASSES = {
    "actuarial_memo",
    "exception_page",
    "rate_manual",
    "rate_indication",
    "trend_exhibit",
    "ldf_exhibit",
    "experience_exhibit",
    "expense_exhibit",
    "profit_exhibit",
    "lcm_exhibit",
}

CONTEXT_CLASSES = {
    "objection_letter",
    "company_response",
    "filing_summary",
    "rule_manual",
    "form_schedule",
    "form",
    "iso_reference_list",
}

STORE_ONLY_CLASSES = {
    "authorization_letter",
    "approval_letter",
}


@dataclass(frozen=True)
class ParseDecision:
    document_class: str
    extraction_route: str
    value_tier: str
    native_text_chars: int
    page_count: int
    table_like_score: int
    ocr_needed: bool
    ocr_used: bool
    route_reason: str


def decide_parse_route(
    *,
    file_type: str,
    pages: list[PageText],
    document_class: str,
    failures: list[str],
) -> ParseDecision:
    full_text = "\n".join(page.text for page in pages)
    native_text_chars = len(full_text.strip())
    page_count = len(pages)
    avg_chars_per_page = native_text_chars / page_count if page_count else 0
    table_like_score = _table_like_score(full_text)
    ocr_used = any(page.ocr_used for page in pages)
    value_tier = _value_tier(document_class)
    normalized_type = file_type.lower().strip(".")

    if failures or not pages:
        return ParseDecision(
            document_class=document_class,
            extraction_route="parse_failed",
            value_tier=value_tier,
            native_text_chars=native_text_chars,
            page_count=page_count,
            table_like_score=table_like_score,
            ocr_needed=True,
            ocr_used=ocr_used,
            route_reason="Parser returned no usable pages or reported failures.",
        )

    if normalized_type in {"xlsx", "xls", "csv"}:
        route = "spreadsheet_structured"
        reason = "Spreadsheet-like source; preserve tabular structure and extract cells by sheet/range."
        ocr_needed = False
    elif normalized_type in {"docx", "doc"}:
        route = "document_text"
        reason = "Word-processing source with directly extractable text."
        ocr_needed = False
    elif normalized_type != "pdf":
        route = "plain_text_or_unknown"
        reason = "Non-PDF attachment; extract available text and keep original for review."
        ocr_needed = False
    elif avg_chars_per_page < 20:
        route = "ocr_required"
        reason = "PDF has almost no native text per page; likely scanned image content."
        ocr_needed = True
    elif avg_chars_per_page < 100:
        route = "native_text_weak_review"
        reason = "PDF has sparse native text; use extracted text but queue for OCR/layout review if high value."
        ocr_needed = value_tier == "high_value_actuarial"
    elif table_like_score >= 3:
        route = "native_text_table_aware"
        reason = "PDF has usable native text plus numeric/table-like lines; parse text and preserve table context."
        ocr_needed = False
    else:
        route = "native_text"
        reason = "PDF has sufficient native text for direct extraction."
        ocr_needed = False

    if value_tier == "store_only" and route.startswith("native_text"):
        route = "native_text_store_only"
        reason = f"{reason} Administrative/supporting document; save for provenance and search, not primary actuarial facts."

    return ParseDecision(
        document_class=document_class,
        extraction_route=route,
        value_tier=value_tier,
        native_text_chars=native_text_chars,
        page_count=page_count,
        table_like_score=table_like_score,
        ocr_needed=ocr_needed,
        ocr_used=ocr_used,
        route_reason=reason,
    )


def _value_tier(document_class: str) -> str:
    if document_class in HIGH_VALUE_CLASSES:
        return "high_value_actuarial"
    if document_class in CONTEXT_CLASSES:
        return "useful_context"
    if document_class in STORE_ONLY_CLASSES:
        return "store_only"
    return "review_queue"


def _table_like_score(text_value: str) -> int:
    score = 0
    numeric_pattern = re.compile(r"[-$]?\d[\d,.]*%?")
    for line in text_value.splitlines():
        number_count = len(numeric_pattern.findall(line))
        has_table_separator = "|" in line or "\t" in line
        if number_count >= 3 or (number_count >= 2 and has_table_separator):
            score += 1
    return score
