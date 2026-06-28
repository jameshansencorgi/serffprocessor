from __future__ import annotations

import re

from serff_intel.extract.fact_keys import canonical_fact_key
from serff_intel.extract.schemas import EvidenceFact


# Label-only patterns. The value is selected separately so a distractor percent
# (e.g. a credibility weight) sitting between the label and the real figure is skipped.
PERCENT_LABELS: list[tuple[str, str, re.Pattern[str]]] = [
    ("requested_rate_change", "requested", re.compile(r"(?:requested|proposed)\s+(?:rate\s+)?(?:level\s+)?(?:change|impact|increase|decrease)", re.I)),
    ("requested_rate_change", "requested", re.compile(r"overall\s+(?:rate\s+)?(?:level\s+)?(?:change|impact|increase|decrease)", re.I)),
    ("approved_rate_change", "approved", re.compile(r"approved\s+(?:rate\s+)?(?:level\s+)?(?:change|impact|increase|decrease)", re.I)),
    ("indicated_rate_level_change", "indicated", re.compile(r"indicated\s+(?:rate\s+)?(?:level\s+)?change", re.I)),
    ("selected_rate_level_change", "selected", re.compile(r"selected\s+(?:rate\s+)?(?:level\s+)?change", re.I)),
    ("loss_trend", "unknown", re.compile(r"loss\s+trend", re.I)),
    ("frequency_trend", "unknown", re.compile(r"(?:selected\s+|indicated\s+)?(?:annual\s+)?(?:claim\s+)?frequency\s+trend", re.I)),
    ("severity_trend", "unknown", re.compile(r"(?:selected\s+|indicated\s+)?(?:annual\s+)?(?:claim\s+)?severity\s+trend", re.I)),
    ("expense_provision", "unknown", re.compile(r"expense\s+provision", re.I)),
    ("profit_provision", "indicated", re.compile(r"indicated\s+underwriting\s+profit\s+provision", re.I)),
    ("profit_provision", "selected", re.compile(r"selected\s+underwriting\s+profit\s+provision", re.I)),
    ("profit_provision", "selected", re.compile(r"profit\s+load", re.I)),
    ("profit_provision", "unknown", re.compile(r"profit\s+provision", re.I)),
    # Expense / profit / permissible-loss ratio line items (Exhibit E/G blocks).
    # Each pattern matches only the label; the percent value is selected by _select_percent_value.
    ("commission_expense_ratio", "unknown", re.compile(r"commission\s+&\s+brokerage\s+expenses", re.I)),
    ("other_acquisition_expense_ratio", "unknown", re.compile(r"other\s+acquisition\s+expenses", re.I)),
    ("general_expense_ratio", "unknown", re.compile(r"general\s+expenses", re.I)),
    ("taxes_licenses_fees_ratio", "unknown", re.compile(r"taxes,?\s+licenses\s+&\s+fees", re.I)),
    # Standalone "Profit" line item (e.g. "f) Profit 9.0%").
    # Three guards, all load-bearing on real SERFF Exhibit E/G/R pages:
    #   (?<!&\s)  -> blocks "Total Expenses & Profit 41.9%" (that 41.9% is the combined
    #               expense+profit total, not the profit provision itself).
    #   (?<!\w\s) -> blocks a word+space before "profit", i.e. "Underwriting Profit". This is
    #               deliberately conservative: on the Brazos/Accredited Exhibit R pages the
    #               phrase "Underwriting Profit" appears not only on the genuine pre-tax
    #               provision line but also on tax lines we must NOT capture — e.g. "Federal
    #               Income Tax on Underwriting Profit = (6) x 21%" (21% is the tax rate) and
    #               "Underwriting Profit After Federal Income Tax ... 7.1%" (after-tax figure,
    #               not the ratemaking provision). Dropping this guard to catch a clean
    #               "Underwriting Profit 9.0%" line re-introduces those false positives, so we
    #               keep it: the pre-tax 9.0% provision is still captured elsewhere via the
    #               "Profit Load" pattern, and a missing fact is preferable to a wrong one.
    #   (?!\s*(?:provision|load|margin)) -> blocks "profit provision/load/margin", which are
    #               already captured by the more specific patterns above (avoids a duplicate
    #               fact for the same figure).
    ("profit_provision", "unknown", re.compile(r"(?<!&\s)(?<!\w\s)\bprofit\b(?!\s*(?:provision|load|margin))", re.I)),
    ("permissible_loss_ratio", "unknown", re.compile(r"permissible\s+loss\s+(?:&\s+lae\s+)?ratio(?!\s+in\s+decimal)", re.I)),
    ("expected_loss_ratio", "unknown", re.compile(r"expected\s+loss\s+ratio", re.I)),
]

WRITTEN_PREMIUM_RE = re.compile(r"written\s+premium\s+impact[^\n$0-9-]{0,80}(\$?-?\d[\d,]*(?:\.\d+)?)", re.I)
PERCENT_TOKEN_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s?%")
DISTRACTOR_CUES = ("credibility", "confidence", "complement", "weight", "probability", "z-value", "z value")
# Credibility is captured inline (value must be an adjacent percent) because it is often
# a bare decimal (Z = 0.60); a forward scan would otherwise grab a later rate-change %.
CREDIBILITY_RE = re.compile(r"credibility\s+(?:of|is|at|=|:)\s*\(?(-?\d+(?:\.\d+)?)\s?%", re.I)

LCM_RE = re.compile(r"(?:indicated|selected|prior|rounded|offset|used\s+immediately\s+prior)?[^\n]{0,80}(?:loss\s+cost\s+multiplier|LCM)[^\n]{0,160}", re.I)
DECIMAL_RE = re.compile(r"\d+\.\d{2,4}")


def extract_rate_facts(text: str, page_number: int | None = None) -> list[EvidenceFact]:
    facts: list[EvidenceFact] = []
    for fact_type, role, label_pattern in PERCENT_LABELS:
        for match in label_pattern.finditer(text):
            value, value_start, selector_review_reason = _select_percent_value(text, match.end())
            if value is None or value_start is None:
                continue
            inferred_role = _role_from_context(match.group(0), default=role)
            normalized = _normalize_percent_or_money(value)
            if _is_parenthesized_negative(text, value_start, value):
                normalized = f"-{normalized}"
            role_unknown = inferred_role == "unknown" and fact_type in _ROLE_REQUIRED_FACTS
            facts.append(
                EvidenceFact(
                    fact_type=fact_type,
                    fact_key=canonical_fact_key(fact_type),
                    fact_value=value,
                    normalized_value=normalized,
                    unit="percent",
                    role=inferred_role,
                    scope="overall" if "overall" in match.group(0).lower() else None,
                    confidence=0.78,
                    needs_review=role_unknown or selector_review_reason is not None,
                    review_reason=_review_reason(role_unknown, selector_review_reason),
                    evidence_text=_window(text, match.start(), value_start + len(value)),
                    page_number=page_number,
                    extraction_method="regex:rate_impact",
                )
            )
    facts.extend(_extract_written_premium_facts(text, page_number))
    facts.extend(_extract_credibility_facts(text, page_number))
    facts.extend(_extract_lcm_facts(text, page_number))
    return facts


def _select_percent_value(
    text: str, label_end: int, window: int = 80
) -> tuple[str | None, int | None, str | None]:
    """Pick the percent value attached to a label, skipping distractor percents.

    Returns ``(value, absolute_value_start, review_reason)``. A distractor is a
    percent whose immediately-preceding phrase names something other than the rated
    quantity (e.g. a credibility weight). The extractor still returns a best guess
    when possible, but marks the fact for review if it skipped distractors or saw
    multiple plausible values.
    """
    region = text[label_end : label_end + window]
    # Don't let the scan reach into the next sentence/section: a bare "." inside a
    # decimal (12.4) is not a boundary, but a sentence-ending "." (followed by space)
    # or a newline is. Prevents "requested rate impact." grabbing a later "...10.1%".
    boundary = re.search(r"[.;]\s|\n", region)
    if boundary is not None:
        region = region[: boundary.start()]
    fallback: tuple[str, int] | None = None
    plausible: list[tuple[str, int]] = []
    skipped_distractor = False
    prev_end = 0
    for token in PERCENT_TOKEN_RE.finditer(region):
        preceding = region[prev_end : token.start()].lower()
        value = token.group(1)
        value_start = label_end + token.start(1)
        if fallback is None:
            fallback = (value, value_start)
        if any(cue in preceding for cue in DISTRACTOR_CUES):
            skipped_distractor = True
        else:
            plausible.append((value, value_start))
        prev_end = token.end()
    if len(plausible) == 1:
        value, value_start = plausible[0]
        return value, value_start, "distractor_number" if skipped_distractor else None
    if len(plausible) > 1:
        value, value_start = plausible[0]
        return value, value_start, "ambiguous_percent_candidates"
    if fallback is not None:
        return fallback[0], fallback[1], "distractor_number"
    return None, None, None


def _extract_written_premium_facts(text: str, page_number: int | None = None) -> list[EvidenceFact]:
    facts: list[EvidenceFact] = []
    for match in WRITTEN_PREMIUM_RE.finditer(text):
        value = match.group(1)
        normalized = _normalize_percent_or_money(value)
        if _is_parenthesized_negative(text, match.start(1), value):
            normalized = f"-{normalized}"
        facts.append(
            EvidenceFact(
                fact_type="written_premium_impact",
                fact_key=canonical_fact_key("written_premium_impact"),
                fact_value=value,
                normalized_value=normalized,
                unit="dollars",
                role="unknown",
                confidence=0.78,
                needs_review=False,
                evidence_text=_window(text, match.start(), match.end()),
                page_number=page_number,
                extraction_method="regex:rate_impact",
            )
        )
    return facts


def _extract_credibility_facts(text: str, page_number: int | None = None) -> list[EvidenceFact]:
    facts: list[EvidenceFact] = []
    for match in CREDIBILITY_RE.finditer(text):
        value = match.group(1)
        facts.append(
            EvidenceFact(
                fact_type="credibility",
                fact_key=canonical_fact_key("credibility"),
                fact_value=value,
                normalized_value=_normalize_percent_or_money(value),
                unit="percent",
                role="unknown",
                confidence=0.78,
                needs_review=False,
                evidence_text=_window(text, match.start(), match.end()),
                page_number=page_number,
                extraction_method="regex:rate_impact",
            )
        )
    return facts


def _review_reason(role_unknown: bool, selector_review_reason: str | None) -> str | None:
    if selector_review_reason:
        return selector_review_reason
    if role_unknown:
        return "ambiguous_role"
    return None


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
                fact_key=canonical_fact_key("loss_cost_multiplier"),
                fact_value=value,
                normalized_value=value,
                unit="factor",
                role=role,
                confidence=0.78,
                needs_review=role == "unknown",
                review_reason="ambiguous_role" if role == "unknown" else None,
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


def _is_parenthesized_negative(text: str, value_start: int, value: str) -> bool:
    """Accounting notation wraps a decrease in parentheses, e.g. ``(5.0%)`` means ``-5.0``."""
    if value.startswith("-"):
        return False
    return value_start > 0 and text[value_start - 1] == "("


def _normalize_percent_or_money(value: str) -> str:
    return value.replace("$", "").replace(",", "").strip()


def _window(text: str, start: int, end: int, radius: int = 180) -> str:
    return " ".join(text[max(0, start - radius) : min(len(text), end + radius)].split())
