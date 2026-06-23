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

