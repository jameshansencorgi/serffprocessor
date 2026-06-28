from __future__ import annotations

import re

from serff_intel.extract.schemas import EvidenceFact


RATE_PATTERNS: list[tuple[str, str, str, re.Pattern[str]]] = [
    ("requested_rate_change", "requested", "percent", re.compile(r"(?:requested|proposed)\s+(?:rate\s+)?(?:level\s+)?(?:change|impact|increase|decrease)[^\n%]{0,80}?(-?\d+(?:\.\d+)?)\s?%", re.I)),
    ("requested_rate_change", "requested", "percent", re.compile(r"overall\s+(?:rate\s+)?(?:level\s+)?(?:change|impact|increase|decrease)[^\n%]{0,80}?(-?\d+(?:\.\d+)?)\s?%", re.I)),
    ("approved_rate_change", "approved", "percent", re.compile(r"approved\s+(?:rate\s+)?(?:level\s+)?(?:change|impact|increase|decrease)[^\n%]{0,80}?(-?\d+(?:\.\d+)?)\s?%", re.I)),
    ("indicated_rate_level_change", "indicated", "percent", re.compile(r"indicated\s+(?:rate\s+)?level\s+change[^\n%]{0,80}?(-?\d+(?:\.\d+)?)\s?%", re.I)),
    ("selected_rate_level_change", "selected", "percent", re.compile(r"selected\s+(?:rate\s+)?level\s+change[^\n%]{0,80}?(-?\d+(?:\.\d+)?)\s?%", re.I)),
    ("written_premium_impact", "unknown", "dollars", re.compile(r"written\s+premium\s+impact[^\n$0-9-]{0,80}(\$?-?\d[\d,]*(?:\.\d+)?)", re.I)),
    ("loss_trend", "unknown", "percent", re.compile(r"loss\s+trend[^\n%]{0,80}?(-?\d+(?:\.\d+)?)\s?%", re.I)),
    ("expense_provision", "unknown", "percent", re.compile(r"expense\s+provision[^\n%]{0,80}?(-?\d+(?:\.\d+)?)\s?%", re.I)),
    ("profit_provision", "indicated", "percent", re.compile(r"indicated\s+underwriting\s+profit\s+provision[^\n%]{0,80}?(-?\d+(?:\.\d+)?)\s?%", re.I)),
    ("profit_provision", "selected", "percent", re.compile(r"selected\s+underwriting\s+profit\s+provision[^\n%]{0,80}?(-?\d+(?:\.\d+)?)\s?%", re.I)),
    ("profit_provision", "selected", "percent", re.compile(r"profit\s+load[^\n%]{0,80}?(-?\d+(?:\.\d+)?)\s?%", re.I)),
    ("profit_provision", "unknown", "percent", re.compile(r"profit\s+provision[^\n%]{0,80}?(-?\d+(?:\.\d+)?)\s?%", re.I)),
]

LCM_RE = re.compile(r"(?:indicated|selected|prior|rounded|offset|used\s+immediately\s+prior)?[^\n]{0,80}(?:loss\s+cost\s+multiplier|LCM)[^\n]{0,160}", re.I)
DECIMAL_RE = re.compile(r"\d+\.\d{2,4}")


def extract_rate_facts(text: str, page_number: int | None = None) -> list[EvidenceFact]:
    facts: list[EvidenceFact] = []
    for fact_type, role, unit, pattern in RATE_PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(1)
            inferred_role = _role_from_context(match.group(0), default=role)
            facts.append(
                EvidenceFact(
                    fact_type=fact_type,
                    fact_value=value,
                    normalized_value=_normalize_percent_or_money(value),
                    unit=unit,
                    role=inferred_role,
                    scope="overall" if "overall" in match.group(0).lower() else None,
                    confidence=0.78,
                    needs_review=inferred_role == "unknown" and fact_type in _ROLE_REQUIRED_FACTS,
                    evidence_text=_window(text, match.start(), match.end()),
                    page_number=page_number,
                    extraction_method="regex:rate_impact",
                )
            )
    facts.extend(_extract_lcm_facts(text, page_number))
    return facts


def _extract_lcm_facts(text: str, page_number: int | None = None) -> list[EvidenceFact]:
    facts: list[EvidenceFact] = []
    seen: set[tuple[str, str, str]] = set()
    for match in LCM_RE.finditer(text):
        snippet = match.group(0)
        decimals = DECIMAL_RE.findall(snippet)
        if not decimals:
            continue
        value = decimals[-1]
        role = _role_from_context(snippet, default="unknown")
        evidence = _window(text, match.start(), match.end())
        key = (value, role, evidence)
        if key in seen:
            continue
        seen.add(key)
        facts.append(
            EvidenceFact(
                fact_type="loss_cost_multiplier",
                fact_value=value,
                normalized_value=value,
                unit="factor",
                role=role,
                confidence=0.78,
                needs_review=role == "unknown",
                evidence_text=evidence,
                page_number=page_number,
                extraction_method="regex:rate_impact",
            )
        )
    return facts


_ROLE_REQUIRED_FACTS = {
    "requested_rate_change",
    "approved_rate_change",
    "indicated_rate_level_change",
    "selected_rate_level_change",
    "loss_cost_multiplier",
    "profit_provision",
}


def _role_from_context(text_value: str, default: str = "unknown") -> str:
    lower = text_value.lower()
    if re.search(r"selected\s+loss\s+cost\s+multiplier|selected\s+underwriting\s+profit", lower):
        return "selected"
    if "used immediately prior" in lower or "prior" in lower:
        return "prior"
    if "approved" in lower:
        return "approved"
    if "requested" in lower or "proposed" in lower:
        return "requested"
    if "rounded" in lower:
        return "rounded"
    if "offset" in lower:
        return "offset"
    if "indicated" in lower:
        return "indicated"
    if "selected" in lower:
        return "selected"
    if "filed" in lower:
        return "filed"
    if "final" in lower:
        return "final"
    return default


def _normalize_percent_or_money(value: str) -> str:
    return value.replace("$", "").replace(",", "").strip()


def _window(text: str, start: int, end: int, radius: int = 180) -> str:
    return " ".join(text[max(0, start - radius) : min(len(text), end + radius)].split())
