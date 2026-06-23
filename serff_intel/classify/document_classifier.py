from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentClassification:
    document_class: str
    confidence: float
    matched_keywords: list[str]


RULES: list[tuple[str, tuple[str, ...]]] = [
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


def classify_document(filename: str, text: str) -> DocumentClassification:
    haystack = f"{filename}\n{text[:8000]}".lower()
    best_class = "unknown"
    best_matches: list[str] = []
    for document_class, keywords in RULES:
        matches = [keyword for keyword in keywords if keyword in haystack]
        if len(matches) > len(best_matches):
            best_class = document_class
            best_matches = matches
    confidence = min(0.95, 0.45 + 0.15 * len(best_matches)) if best_matches else 0.2
    return DocumentClassification(best_class, confidence, best_matches)

