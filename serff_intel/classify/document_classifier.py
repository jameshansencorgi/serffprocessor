from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentClassification:
    document_class: str
    confidence: float
    matched_keywords: list[str]


RULES: list[tuple[str, tuple[str, ...]]] = [
    ("authorization_letter", ("authorization letter", "letter of authorization", "authorized to file", "authorization to file")),
    ("exception_page", ("exception page", "exception pages", "auto exception", "commercial auto exception")),
    ("iso_reference_list", ("iso lc", "iso loss cost", "rule circular", "circular adoption", "adoptions list")),
    ("rate_indication", ("rate indication", "indicated rate", "selected rate", "overall indicated", "overall selected", "exhibit c")),
    ("trend_exhibit", ("frequency and severity trend", "frequency trend", "severity trend", "loss trend selection", "trend selections")),
    ("ldf_exhibit", ("ldf", "loss development factor", "development factor selection", "selected development factor")),
    ("experience_exhibit", ("historical experience", "earned premium", "incurred losses", "loss ratio", "policy count", "vehicle count", "exhibit d")),
    ("expense_exhibit", ("expense provision", "expense information", "commission expense", "general expense", "taxes licenses and fees", "exhibit e")),
    ("profit_exhibit", ("profit provision", "return on equity", "roe", "underwriting profit", "target surplus", "exhibit l")),
    ("lcm_exhibit", ("loss cost multiplier", "lcm", "exhibit g")),
    ("actuarial_memo", ("actuarial memorandum", "actuarial memo", "indicated rate level", "selected rate level")),
    ("objection_letter", ("objection letter", "objection:", "department objection", "consumer protection objection")),
    ("company_response", ("company response", "response to objection", "insurer response")),
    ("approval_letter", ("approved", "approval letter", "filing approved", "department has approved")),
    ("rate_manual", ("rate manual", "base rate", "loss cost multiplier", "territory factor")),
    ("rule_manual", ("rule manual", "underwriting rule", "rating rule", "eligibility rule")),
    ("form_schedule", ("form schedule", "schedule of forms")),
    ("filing_summary", ("serff tracking", "disposition", "submitted date", "filing type")),
    ("exhibit", ("exhibit", "supporting exhibit", "rate indication")),
    ("form", ("policy form", "endorsement", "coverage form")),
]

BROAD_FALLBACK_CLASSES = {"exhibit", "filing_summary", "form"}


def classify_document(filename: str, text: str) -> DocumentClassification:
    filename_haystack = filename.lower()
    text_haystack = text[:8000].lower()
    best_class = "unknown"
    best_matches: list[str] = []
    best_score = 0
    for document_class, keywords in RULES:
        filename_matches = [keyword for keyword in keywords if keyword in filename_haystack]
        text_matches = [keyword for keyword in keywords if keyword in text_haystack]
        matches = sorted(set(filename_matches + text_matches))
        filename_weight = 1 if document_class in BROAD_FALLBACK_CLASSES else 3
        score = len(text_matches) + filename_weight * len(filename_matches)
        if score > best_score:
            best_class = document_class
            best_matches = matches
            best_score = score
    confidence = min(0.95, 0.45 + 0.10 * best_score) if best_matches else 0.2
    return DocumentClassification(best_class, confidence, best_matches)
