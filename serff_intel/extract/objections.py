from __future__ import annotations

import re

from serff_intel.extract.schemas import EvidenceFact


OBJECTION_RE = re.compile(r"(.{0,80}\bobjection\b.{0,500})", re.I | re.S)


def extract_objection_facts(text: str, page_number: int | None = None) -> list[EvidenceFact]:
    facts: list[EvidenceFact] = []
    for match in OBJECTION_RE.finditer(text):
        evidence = " ".join(match.group(1).split())
        facts.append(
            EvidenceFact(
                fact_type="regulator_objection",
                fact_value=evidence[:500],
                normalized_value=None,
                confidence=0.72,
                evidence_text=evidence,
                page_number=page_number,
                extraction_method="regex:objections",
            )
        )
    return facts


_TOPIC_CUES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("trend", ("trend",)),
    ("credibility", ("credibility", "complement")),
    ("catastrophe", ("catastrophe", "cat load", "modeled cat", "hurricane")),
    ("reinsurance", ("reinsurance",)),
    ("expense", ("expense", "commission", "taxes, licenses")),
    ("profit", ("profit", "return on equity", "roe")),
    ("rate_level", ("rate level", "indicated rate", "selected rate", "rate change")),
    ("data_quality", ("data quality", "missing data", "data is")),
)

_RESPONSE_MARKER = re.compile(
    r"\n\s*(?:company\s+response|insurer\s+response|response\s+to\s+objection|company\s+reply)\s*:?\s*\n?",
    re.I,
)


def classify_objection_topic(text: str) -> str:
    """Map regulator-objection text to a controlled topic (see ``enums.OBJECTION_TOPICS``)."""
    lower = text.lower()
    for topic, cues in _TOPIC_CUES:
        if any(cue in lower for cue in cues):
            return topic
    return "general"


def split_objection_and_response(text: str) -> tuple[str, str | None]:
    """Split a combined objection/response blob into ``(objection, company_response_or_None)``."""
    marker = _RESPONSE_MARKER.search(text)
    if marker is None:
        return text.strip(), None
    objection = text[: marker.start()].strip()
    response = text[marker.end() :].strip()
    return objection, response or None

