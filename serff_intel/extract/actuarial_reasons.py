from __future__ import annotations

from serff_intel.extract.schemas import EvidenceFact


# Qualitative narrative drivers only. Quantitative cues (frequency/severity trend,
# credibility, loss trend) are now numeric extractors in rate_impact.py, so they no
# longer enter the review queue as keyword-as-value "unknown" facts.
REASON_KEYWORDS: dict[str, tuple[str, ...]] = {
    "social_inflation": ("social inflation",),
    "nuclear_verdicts": ("nuclear verdict", "large verdict", "runaway verdict"),
    "litigation": ("litigation", "attorney representation", "lawsuit"),
    "telematics": ("telematics", "usage based", "usage-based"),
    "new_ventures": ("new venture", "new ventures"),
    "trucking": ("trucking", "truckers", "motor carrier"),
}


def extract_reason_facts(text: str, page_number: int | None = None) -> list[EvidenceFact]:
    lower = text.lower()
    facts: list[EvidenceFact] = []
    for fact_type, keywords in REASON_KEYWORDS.items():
        for keyword in keywords:
            idx = lower.find(keyword)
            if idx < 0:
                continue
            facts.append(
                EvidenceFact(
                    fact_type=fact_type,
                    fact_value=keyword,
                    normalized_value=keyword.replace("-", " "),
                    confidence=0.7,
                    evidence_text=_sentence_window(text, idx),
                    page_number=page_number,
                    extraction_method="keyword:actuarial_reasons",
                )
            )
            break
    return facts


def _sentence_window(text: str, idx: int, radius: int = 240) -> str:
    return " ".join(text[max(0, idx - radius) : min(len(text), idx + radius)].split())

