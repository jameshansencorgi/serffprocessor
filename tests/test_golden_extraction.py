"""Golden-set regression gates for the build->test->improve loop.

The full scoreboard lives in scripts/score_extraction.py. These tests pin the
behaviours we've fixed so they can't regress. The corpus under data/processed/text
is gitignored, so the corpus-backed tests skip gracefully when it's absent.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from serff_intel.extract.actuarial_reasons import extract_reason_facts
from serff_intel.extract.objections import extract_objection_facts
from serff_intel.extract.rate_impact import extract_rate_facts

ROOT = Path(__file__).resolve().parents[1]
TEXTDIR = ROOT / "data/processed/text"
GOLDEN = yaml.safe_load((ROOT / "tests/golden/expected_facts.yml").read_text())


def _trucking(text: str) -> list:
    return [f for f in extract_reason_facts(text) if f.fact_type == "trucking"]


def test_trucking_skips_all_caps_heading() -> None:
    # "24. TRUCKERS" is an all-caps rating-manual heading, not a narrative driver.
    assert not _trucking("24. TRUCKERS\nPolicy Writing Minimum Premium $21.")
    # A genuine prose mention still tags.
    assert _trucking("The book is predominantly long-haul trucking risk.")


def test_coverage_lcm_matrix_extracted() -> None:
    text = (
        "1. LOSS COST MULTIPLIER\n"
        "The following loss cost multipliers (LCM) will apply to the ISO loss costs:\n"
        "Coverage LCM\n"
        "Liability 2.002\n"
        "Physical Damage 2.002\n"
        "2. MINIMUM PREMIUMS\n"
    )
    lcms = [f for f in extract_rate_facts(text) if f.fact_type == "loss_cost_multiplier"]
    assert any(f.normalized_value == "2.002" and f.coverage == "AL" for f in lcms)
    assert any(f.normalized_value == "2.002" and f.coverage == "APD" for f in lcms)


def test_exhibit_c_total_statewide_change_extracted() -> None:
    # Exhibit C / PC365 summary line: the statewide overall rate change.
    facts = extract_rate_facts("3. Total Statewide Change 47.5% 47.5%\n")
    rc = [f for f in facts if f.fact_type == "requested_rate_change"]
    assert rc and rc[0].normalized_value == "47.5"


def test_coverage_lcm_does_not_fire_outside_lcm_section() -> None:
    # A "<label> <decimal>" line with no LCM section header must not become an LCM fact.
    text = "Some Random Heading\nLiability 2.002\nPhysical Damage 2.002\n"
    coverage_lcms = [
        f for f in extract_rate_facts(text) if f.fact_type == "loss_cost_multiplier" and f.coverage
    ]
    assert not coverage_lcms


def test_repeated_identical_percents_not_flagged_ambiguous() -> None:
    # A trend row repeats the same value across year columns -> not ambiguous.
    facts = extract_rate_facts("Frequency Trend 3.6% 3.6% 3.6% 3.6%\n")
    freq = [f for f in facts if f.fact_type == "frequency_trend"]
    assert freq and freq[0].normalized_value == "3.6"
    assert freq[0].needs_review is False
    assert freq[0].review_reason is None


def test_distinct_percents_still_flagged_ambiguous() -> None:
    # Different values in the window remain genuinely ambiguous.
    facts = extract_rate_facts("Total Statewide Change 47.5% 12.0%\n")
    rc = [f for f in facts if f.fact_type == "requested_rate_change"]
    assert rc and rc[0].review_reason == "ambiguous_percent_candidates"


def _num(value: str | None) -> float | None:
    if value is None:
        return None
    cleaned = value.replace("$", "").replace(",", "").replace("%", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _facts(doc: str):
    text = (TEXTDIR / f"{doc}.txt").read_text()
    return extract_rate_facts(text) + extract_reason_facts(text) + extract_objection_facts(text)


def _has(facts, key: str, value=None) -> bool:
    for f in facts:
        if key in (f.fact_key, f.fact_type):
            if value is None:
                return True
            fv = _num(f.normalized_value)
            if fv is not None and abs(fv - float(value)) < 0.01:
                return True
    return False


@pytest.mark.skipif(not TEXTDIR.exists(), reason="processed corpus not present (gitignored)")
def test_golden_false_positive_guards() -> None:
    failures = []
    for doc, checks in GOLDEN.get("must_not", {}).items():
        facts = _facts(doc)
        for c in checks:
            if _has(facts, c["key"], c.get("value")):
                failures.append(f"{doc}: must NOT have {c['key']}={c.get('value')}")
    assert not failures, failures


@pytest.mark.skipif(not TEXTDIR.exists(), reason="processed corpus not present (gitignored)")
def test_golden_prose_anchor_recall() -> None:
    misses = []
    for doc, anchors in GOLDEN["anchors"].items():
        facts = _facts(doc)
        for a in anchors:
            if a.get("table_borne"):
                continue
            if not _has(facts, a["key"], a.get("value")):
                misses.append(f"{doc}: {a['key']}={a.get('value')}")
    assert not misses, misses
