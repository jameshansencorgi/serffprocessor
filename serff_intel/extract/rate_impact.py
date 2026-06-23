from __future__ import annotations

import re

from serff_intel.extract.schemas import EvidenceFact


RATE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("requested_rate_change", re.compile(r"(?:requested|proposed|overall)\s+(?:rate\s+)?(?:level\s+)?(?:change|impact|increase|decrease)[^\n%]{0,80}?(-?\d+(?:\.\d+)?)\s?%", re.I)),
    ("approved_rate_change", re.compile(r"approved\s+(?:rate\s+)?(?:level\s+)?(?:change|impact|increase|decrease)[^\n%]{0,80}?(-?\d+(?:\.\d+)?)\s?%", re.I)),
    ("indicated_rate_level_change", re.compile(r"indicated\s+(?:rate\s+)?level\s+change[^\n%]{0,80}?(-?\d+(?:\.\d+)?)\s?%", re.I)),
    ("selected_rate_level_change", re.compile(r"selected\s+(?:rate\s+)?level\s+change[^\n%]{0,80}?(-?\d+(?:\.\d+)?)\s?%", re.I)),
    ("written_premium_impact", re.compile(r"written\s+premium\s+impact[^\n$0-9-]{0,80}(\$?-?\d[\d,]*(?:\.\d+)?)", re.I)),
    ("loss_trend", re.compile(r"loss\s+trend[^\n%]{0,80}?(-?\d+(?:\.\d+)?)\s?%", re.I)),
    ("expense_provision", re.compile(r"expense\s+provision[^\n%]{0,80}?(-?\d+(?:\.\d+)?)\s?%", re.I)),
    ("profit_provision", re.compile(r"(?:selected\s+underwriting\s+profit\s+provision|profit\s+load|underwriting\s+profit\s+provision|profit\s+provision)[^\n%]{0,80}?(-?\d+(?:\.\d+)?)\s?%", re.I)),
]

LCM_RE = re.compile(r"(?:loss\s+cost\s+multiplier|LCM)[^\n]{0,160}", re.I)
DECIMAL_RE = re.compile(r"\d+\.\d{2,4}")


def extract_rate_facts(text: str, page_number: int | None = None) -> list[EvidenceFact]:
    facts: list[EvidenceFact] = []
    for fact_type, pattern in RATE_PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(1)
            facts.append(
                EvidenceFact(
                    fact_type=fact_type,
                    fact_value=value,
                    normalized_value=_normalize_percent_or_money(value),
                    confidence=0.78,
                    evidence_text=_window(text, match.start(), match.end()),
                    page_number=page_number,
                    extraction_method="regex:rate_impact",
                )
            )
    facts.extend(_extract_lcm_facts(text, page_number))
    return facts


def _extract_lcm_facts(text: str, page_number: int | None = None) -> list[EvidenceFact]:
    facts: list[EvidenceFact] = []
    seen: set[tuple[str, str]] = set()
    for match in LCM_RE.finditer(text):
        snippet = match.group(0)
        decimals = DECIMAL_RE.findall(snippet)
        if not decimals:
            continue
        value = decimals[-1]
        evidence = _window(text, match.start(), match.end())
        key = (value, evidence)
        if key in seen:
            continue
        seen.add(key)
        facts.append(
            EvidenceFact(
                fact_type="loss_cost_multiplier",
                fact_value=value,
                normalized_value=value,
                confidence=0.78,
                evidence_text=evidence,
                page_number=page_number,
                extraction_method="regex:rate_impact",
            )
        )
    return facts


def _normalize_percent_or_money(value: str) -> str:
    return value.replace("$", "").replace(",", "").strip()


def _window(text: str, start: int, end: int, radius: int = 180) -> str:
    return " ".join(text[max(0, start - radius) : min(len(text), end + radius)].split())
