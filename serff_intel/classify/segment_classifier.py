from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SegmentClassification:
    is_substantive: bool
    function_label: str
    topic_label: str


STRUCTURAL_TERMS = ("table of contents", "index", "copyright", "page intentionally left blank")
PROCESS_TERMS = ("filing memorandum", "authorization letter", "submission", "response to objection")
ENFORCEMENT_TERMS = ("objection", "department", "disapproved", "approved", "compliance")
RATE_TERMS = ("rate", "loss cost", "multiplier", "premium", "profit", "expense", "trend", "indication")
RULE_TERMS = ("rule", "manual", "eligibility", "underwriting", "territory", "class")
FORM_TERMS = ("endorsement", "coverage form", "policy form", "exception page")


def classify_segment(text: str) -> SegmentClassification:
    lowered = text.lower()
    if any(term in lowered for term in STRUCTURAL_TERMS):
        return SegmentClassification(False, "structural", "other")
    if any(term in lowered for term in ENFORCEMENT_TERMS):
        return SegmentClassification(True, "enforcement", _topic_label(lowered))
    if any(term in lowered for term in PROCESS_TERMS):
        return SegmentClassification(False, "process", _topic_label(lowered))
    if any(term in lowered for term in RATE_TERMS):
        return SegmentClassification(True, "rating", _topic_label(lowered))
    if any(term in lowered for term in RULE_TERMS):
        return SegmentClassification(True, "rules", _topic_label(lowered))
    if any(term in lowered for term in FORM_TERMS):
        return SegmentClassification(True, "forms", _topic_label(lowered))
    return SegmentClassification(True, "context", _topic_label(lowered))


def _topic_label(lowered: str) -> str:
    if "commercial auto" in lowered or "auto" in lowered:
        return "commercial_auto"
    if "trucking" in lowered or "truck" in lowered or "motor carrier" in lowered:
        return "trucking"
    if "liability" in lowered:
        return "liability"
    if "physical damage" in lowered:
        return "physical_damage"
    if "objection" in lowered:
        return "regulatory_objection"
    return "other"

