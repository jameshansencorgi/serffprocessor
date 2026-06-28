from __future__ import annotations

from pathlib import Path

import yaml

from serff_intel.extract.rate_impact import extract_rate_facts

ROOT = Path(__file__).resolve().parents[1]


def _catalogue_keys() -> set[str]:
    catalogue = yaml.safe_load((ROOT / "docs/fact_catalogue.yml").read_text())
    return {key for group in catalogue["fact_groups"].values() for key in group["facts"]}


def test_canonical_fact_key_map_only_targets_real_catalogue_keys() -> None:
    from serff_intel.extract.fact_keys import CANONICAL_FACT_KEY

    keys = _catalogue_keys()
    unknown = {ft: fk for ft, fk in CANONICAL_FACT_KEY.items() if fk not in keys}
    assert not unknown, f"fact_key values absent from fact_catalogue.yml: {unknown}"


def test_rate_extractor_sets_canonical_fact_key() -> None:
    facts = extract_rate_facts(
        "The requested overall rate change is 12.4%.\n"
        "The indicated rate level change is 15.8%.\n"
        "The selected rate level change is 12.4%.\n"
    )
    by_type = {fact.fact_type: fact for fact in facts}
    assert by_type["requested_rate_change"].fact_key == "requested_overall_rate_change"
    assert by_type["indicated_rate_level_change"].fact_key == "indicated_rate_change"
    assert by_type["selected_rate_level_change"].fact_key == "selected_rate_change"


def test_rate_extractor_reads_parenthetical_negative_as_decrease() -> None:
    facts = extract_rate_facts("The requested rate change is (5.0%).")
    requested = [fact for fact in facts if fact.fact_type == "requested_rate_change"]
    assert requested
    assert requested[0].normalized_value == "-5.0"


def test_rate_extractor_keeps_plain_positive_change_positive() -> None:
    facts = extract_rate_facts("The requested rate change is 5.0%.")
    requested = [fact for fact in facts if fact.fact_type == "requested_rate_change"]
    assert requested
    assert requested[0].normalized_value == "5.0"


def test_rate_gap_is_requested_minus_approved() -> None:
    from serff_intel.export import rate_gap

    assert rate_gap(12.4, 10.1) == 2.3
    assert rate_gap(None, 10.1) is None
    assert rate_gap(12.4, None) is None


def test_written_premium_gap_and_fact_key_reach_exports(tmp_path: Path) -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session as SASession

    from serff_intel.export import export_actuarial_tables
    from serff_intel.models import Base, ExtractedFact, Filing

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with SASession(engine) as session:
        filing = Filing(
            serff_tracking_number="X-1",
            state="TX",
            rate_impact_requested=12.4,
            rate_impact_approved=10.1,
        )
        session.add(filing)
        session.flush()
        session.add(
            ExtractedFact(
                filing_id=filing.id,
                fact_type="written_premium_impact",
                fact_value="4250000",
                normalized_value="4250000",
                confidence=0.78,
                evidence_text="written premium impact 4250000",
                extraction_method="regex:rate_impact",
            )
        )
        session.add(
            ExtractedFact(
                filing_id=filing.id,
                fact_type="requested_rate_change",
                fact_value="12.4",
                normalized_value="12.4",
                confidence=0.78,
                evidence_text="requested overall rate change 12.4%",
                extraction_method="regex:rate_impact",
            )
        )
        session.commit()
        export_actuarial_tables(session, tmp_path / "exports")

    written_premium = (tmp_path / "exports" / "written_premium_impacts.csv").read_text()
    assert "written_premium_impact" in written_premium
    assert "4250000" in written_premium

    filings_csv = (tmp_path / "exports" / "filings.csv").read_text()
    assert "requested_approved_rate_gap" in filings_csv
    assert "2.3" in filings_csv

    rate_changes = (tmp_path / "exports" / "rate_changes.csv").read_text()
    assert "fact_key" in rate_changes
    assert "requested_overall_rate_change" in rate_changes


def test_review_queue_prioritizes_needs_review_over_confidence(tmp_path: Path) -> None:
    import csv

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session as SASession

    from serff_intel.export import export_review_csv
    from serff_intel.models import Base, ExtractedFact, Filing

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with SASession(engine) as session:
        filing = Filing(serff_tracking_number="X-1", state="TX")
        session.add(filing)
        session.flush()
        # Higher confidence but flagged for review -> must surface first.
        session.add(
            ExtractedFact(
                filing_id=filing.id,
                fact_type="loss_cost_multiplier",
                fact_value="1.234",
                normalized_value="1.234",
                confidence=0.78,
                needs_review=True,
                evidence_text="ambiguous lcm role",
                extraction_method="regex:rate_impact",
            )
        )
        # Lower confidence but not flagged -> must come after.
        session.add(
            ExtractedFact(
                filing_id=filing.id,
                fact_type="trucking",
                fact_value="trucking",
                normalized_value="trucking",
                confidence=0.2,
                needs_review=False,
                evidence_text="mentions trucking",
                extraction_method="keyword:actuarial_reasons",
            )
        )
        session.commit()
        export_review_csv(session, tmp_path / "review" / "facts.csv")
        export_review_csv(session, tmp_path / "review" / "all_facts.csv", include_all=True)

    rows = list(csv.DictReader((tmp_path / "review" / "facts.csv").read_text().splitlines()))
    assert len(rows) == 1
    assert rows[0]["fact_type"] == "loss_cost_multiplier"
    assert rows[0]["needs_review"] == "True"

    all_rows = list(csv.DictReader((tmp_path / "review" / "all_facts.csv").read_text().splitlines()))
    assert len(all_rows) == 2


def test_extractor_roles_are_all_declared_in_enum() -> None:
    from serff_intel.extract.enums import ROLES

    facts = extract_rate_facts(
        "Indicated Loss Cost Multiplier = 2.002\n"
        "Selected Loss Cost Multiplier 1.901\n"
        "Loss Cost Multiplier Q / P 1.234\n"
        "The approved overall rate change is 10.1%.\n"
    )
    emitted_roles = {fact.role for fact in facts if fact.role is not None}
    assert emitted_roles
    assert emitted_roles <= ROLES


def test_review_reasons_are_declared_in_enum() -> None:
    from serff_intel.extract.enums import REVIEW_REASONS

    facts = extract_rate_facts("Loss Cost Multiplier Q / P 1.234\n")
    lcm = [fact for fact in facts if fact.fact_type == "loss_cost_multiplier"]
    assert lcm
    assert lcm[0].needs_review is True
    assert lcm[0].review_reason == "ambiguous_role"
    assert lcm[0].review_reason in REVIEW_REASONS


def test_pipeline_unknown_fact_key_reason_is_declared() -> None:
    # The pipeline (Path 2) tags unmapped facts with this reason; keep it in the shared vocab.
    from serff_intel.extract.enums import REVIEW_REASONS

    assert "unknown_fact_key" in REVIEW_REASONS


def test_rate_extractor_skips_distractor_percent_between_label_and_value() -> None:
    # The credibility 60% sits between the label and the real 12.4% change.
    facts = extract_rate_facts(
        "The selected rate level change, after applying a credibility of 60%, is 12.4%."
    )
    selected = [fact for fact in facts if fact.fact_type == "selected_rate_level_change"]
    assert selected
    assert selected[0].normalized_value == "12.4"
    assert selected[0].needs_review is True
    assert selected[0].review_reason == "distractor_number"


def test_rate_extractor_flags_multiple_plausible_percent_candidates() -> None:
    facts = extract_rate_facts(
        "The selected rate level change is 12.4%, compared with an indicated rate level change of 15.8%."
    )
    selected = [fact for fact in facts if fact.fact_type == "selected_rate_level_change"]
    assert selected
    assert selected[0].normalized_value == "12.4"
    assert selected[0].needs_review is True
    assert selected[0].review_reason == "ambiguous_percent_candidates"


def test_rate_extractor_handles_distractor_before_label() -> None:
    facts = extract_rate_facts(
        "Credibility of 60% supports the indicated rate level change of 15.8%."
    )
    indicated = [fact for fact in facts if fact.fact_type == "indicated_rate_level_change"]
    assert indicated
    assert indicated[0].normalized_value == "15.8"


def test_rate_extractor_normalizes_explicit_negative_percent() -> None:
    facts = extract_rate_facts("The approved rate change is -5.0%.")
    approved = [fact for fact in facts if fact.fact_type == "approved_rate_change"]
    assert approved
    assert approved[0].normalized_value == "-5.0"


def test_written_premium_impact_strips_currency_formatting() -> None:
    facts = extract_rate_facts("Written premium impact: $1,234,567.")
    premium = [fact for fact in facts if fact.fact_type == "written_premium_impact"]
    assert premium
    assert premium[0].normalized_value == "1234567"


def test_numeric_frequency_and_severity_trends_extracted() -> None:
    facts = extract_rate_facts(
        "The selected frequency trend is 2.0%. The severity trend is 6.5%."
    )
    freq = [fact for fact in facts if fact.fact_type == "frequency_trend"]
    sev = [fact for fact in facts if fact.fact_type == "severity_trend"]
    assert freq and freq[0].normalized_value == "2.0"
    assert freq[0].fact_key == "frequency_trend"
    assert freq[0].unit == "percent"
    assert sev and sev[0].normalized_value == "6.5"
    assert sev[0].fact_key == "severity_trend"


def test_credibility_percent_extracted_as_number() -> None:
    facts = extract_rate_facts("The complement of credibility of 60% was applied.")
    cred = [fact for fact in facts if fact.fact_type == "credibility"]
    assert cred and cred[0].normalized_value == "60"
    assert cred[0].fact_key == "credibility"


def test_keyword_tagger_drops_quantitative_cues() -> None:
    from serff_intel.extract.actuarial_reasons import extract_reason_facts

    facts = extract_reason_facts(
        "Claim frequency, claim severity, credibility, and loss trend selection are discussed."
    )
    types = {fact.fact_type for fact in facts}
    assert "frequency" not in types
    assert "severity" not in types
    assert "credibility_method" not in types
    assert "loss_trend_reason" not in types


def test_narrative_keyword_tags_still_emitted() -> None:
    from serff_intel.extract.actuarial_reasons import extract_reason_facts

    facts = extract_reason_facts(
        "Social inflation and nuclear verdicts drive trucking litigation."
    )
    types = {fact.fact_type for fact in facts}
    assert {"social_inflation", "nuclear_verdicts", "trucking", "litigation"} <= types


def test_rate_extractor_does_not_bleed_value_across_sentences() -> None:
    # "requested rate impact" has no value in its own sentence; the 10.1% is the approval's.
    text = (
        "The company reduced the requested rate impact.\n\n"
        "The Department approved an approved rate change of 10.1%."
    )
    facts = extract_rate_facts(text)
    approved = [fact for fact in facts if fact.fact_type == "approved_rate_change"]
    requested = [fact for fact in facts if fact.fact_type == "requested_rate_change"]
    assert approved and approved[0].normalized_value == "10.1"
    assert all(fact.normalized_value != "10.1" for fact in requested)


def test_classify_objection_topic_uses_controlled_vocab() -> None:
    from serff_intel.extract.enums import OBJECTION_TOPICS
    from serff_intel.extract.objections import classify_objection_topic

    assert classify_objection_topic("Please provide additional support for the severity trend.") == "trend"
    assert classify_objection_topic("Explain the credibility complement.") == "credibility"
    assert classify_objection_topic("The department has a general question.") == "general"
    for sample in ("severity trend", "credibility", "expense ratio", "profit provision", "a note"):
        assert classify_objection_topic(sample) in OBJECTION_TOPICS


def test_split_objection_and_response_separates_sections() -> None:
    from serff_intel.extract.objections import split_objection_and_response

    objection, response = split_objection_and_response(
        "Objection Letter\nThe Department objects to the selected rate.\n"
        "Company Response\nThe company provided additional exhibit support."
    )
    assert "objects to the selected rate" in objection
    assert "Company Response" not in objection
    assert response is not None and "additional exhibit support" in response


def test_split_objection_without_response_returns_none() -> None:
    from serff_intel.extract.objections import split_objection_and_response

    objection, response = split_objection_and_response("The Department objects to the trend.")
    assert "objects to the trend" in objection
    assert response is None


def test_trucking_keyword_does_not_trigger_on_commercial_auto_header() -> None:
    from serff_intel.extract.actuarial_reasons import extract_reason_facts

    facts = extract_reason_facts("Commercial Auto Liability rate filing")
    trucking_facts = [f for f in facts if f.fact_type == "trucking"]
    assert not trucking_facts, (
        "'commercial auto' should not trigger a trucking fact; "
        f"got {trucking_facts}"
    )


def test_trucking_keyword_triggers_on_trucking_specific_text() -> None:
    from serff_intel.extract.actuarial_reasons import extract_reason_facts

    facts = extract_reason_facts("long-haul trucking and motor carrier operations")
    trucking_facts = [f for f in facts if f.fact_type == "trucking"]
    assert trucking_facts, (
        "Expected a trucking fact from 'trucking' / 'motor carrier' cue, got none"
    )


def test_indicated_rate_change_without_level_word() -> None:
    # Real filings omit "level": "Indicated Rate Change 116.2%"
    facts = extract_rate_facts("Indicated Rate Change 116.2%")
    indicated = [f for f in facts if f.fact_type == "indicated_rate_level_change"]
    assert indicated, "Expected an indicated_rate_level_change fact but got none"
    assert indicated[0].normalized_value == "116.2"
    assert indicated[0].fact_key == "indicated_rate_change"


def test_selected_rate_change_without_level_word() -> None:
    # Real filings omit "level": "Selected Rate Change 9.0%"
    facts = extract_rate_facts("Selected Rate Change 9.0%")
    selected = [f for f in facts if f.fact_type == "selected_rate_level_change"]
    assert selected, "Expected a selected_rate_level_change fact but got none"
    assert selected[0].normalized_value == "9.0"
    assert selected[0].fact_key == "selected_rate_change"


def test_indicated_rate_level_change_regression() -> None:
    # Regression guard: the "level" form must still be matched.
    facts = extract_rate_facts("The indicated rate level change is 15.8%.")
    indicated = [f for f in facts if f.fact_type == "indicated_rate_level_change"]
    assert indicated, "Regression: indicated rate level change no longer matched"
    assert indicated[0].normalized_value == "15.8"


def test_normalize_disposition_maps_to_controlled_vocab() -> None:
    from serff_intel.extract.enums import DISPOSITIONS
    from serff_intel.extract.entities import normalize_disposition

    assert normalize_disposition("Approved") == "approved"
    assert normalize_disposition("Filed and Used") == "filed_and_used"
    assert normalize_disposition("WITHDRAWN") == "withdrawn"
    assert normalize_disposition(None) is None
    assert normalize_disposition("Totally Novel Status") is None
    assert normalize_disposition("Approved") in DISPOSITIONS


# ---------------------------------------------------------------------------
# Expense / profit / permissible-loss ratio extractors (Exhibit E/G block)
# ---------------------------------------------------------------------------

_EXHIBIT_G_BLOCK = """\
a) Commission & Brokerage Expenses 25.7%
b) Other Acquisition Expenses 0.0%
c) General Expenses 4.6%
d) Taxes, Licenses & Fees 2.6%
e) Premium Discount/Expense Constant 0.0%
f) Profit 9.0%
g) Total Expenses & Profit 41.9%
h) Permissible Loss & LAE Ratio 58.1%
i) Permissible Loss & LAE Ratio in Decimal Form 0.581
"""


def test_exhibit_g_commission_expense_extracted() -> None:
    facts = extract_rate_facts(_EXHIBIT_G_BLOCK)
    commission = [f for f in facts if f.fact_type == "commission_expense_ratio"]
    assert commission, "Expected a commission_expense_ratio fact"
    assert commission[0].normalized_value == "25.7"
    assert commission[0].fact_key == "commission_expense_ratio"


def test_exhibit_g_other_acquisition_expense_extracted() -> None:
    facts = extract_rate_facts(_EXHIBIT_G_BLOCK)
    other = [f for f in facts if f.fact_type == "other_acquisition_expense_ratio"]
    assert other, "Expected an other_acquisition_expense_ratio fact"
    assert other[0].normalized_value == "0.0"
    assert other[0].fact_key == "other_acquisition_expense_ratio"


def test_exhibit_g_general_expense_extracted() -> None:
    facts = extract_rate_facts(_EXHIBIT_G_BLOCK)
    general = [f for f in facts if f.fact_type == "general_expense_ratio"]
    assert general, "Expected a general_expense_ratio fact"
    assert general[0].normalized_value == "4.6"
    assert general[0].fact_key == "general_expense_ratio"


def test_exhibit_g_taxes_licenses_fees_extracted() -> None:
    facts = extract_rate_facts(_EXHIBIT_G_BLOCK)
    taxes = [f for f in facts if f.fact_type == "taxes_licenses_fees_ratio"]
    assert taxes, "Expected a taxes_licenses_fees_ratio fact"
    assert taxes[0].normalized_value == "2.6"
    assert taxes[0].fact_key == "taxes_licenses_fees_ratio"


def test_exhibit_g_permissible_loss_ratio_extracted() -> None:
    facts = extract_rate_facts(_EXHIBIT_G_BLOCK)
    permissible = [f for f in facts if f.fact_type == "permissible_loss_ratio"]
    assert permissible, "Expected a permissible_loss_ratio fact"
    assert permissible[0].normalized_value == "58.1"
    assert permissible[0].fact_key == "permissible_loss_ratio"


def test_exhibit_g_profit_line_extracted_as_profit_provision() -> None:
    facts = extract_rate_facts(_EXHIBIT_G_BLOCK)
    profit_facts = [f for f in facts if f.fact_type == "profit_provision"]
    assert profit_facts, "Expected a profit_provision fact from 'f) Profit 9.0%'"
    values = [f.normalized_value for f in profit_facts]
    assert "9.0" in values, f"Expected profit_provision 9.0 but got {values}"


def test_exhibit_g_total_expenses_profit_not_captured_as_profit_provision() -> None:
    # "g) Total Expenses & Profit 41.9%" must NOT produce a profit_provision fact
    facts = extract_rate_facts(_EXHIBIT_G_BLOCK)
    profit_facts = [f for f in facts if f.fact_type == "profit_provision"]
    bad_values = [f.normalized_value for f in profit_facts if f.normalized_value == "41.9"]
    assert not bad_values, (
        "profit_provision must not capture 41.9 (Total Expenses & Profit line); "
        f"got {bad_values}"
    )


def test_total_expenses_profit_regression_standalone() -> None:
    # Regression: the (?<!&\s) guard must keep blocking "Total Expenses & Profit 41.9%"
    # even as a standalone line — the 41.9% is total expense+profit, not the provision.
    facts = extract_rate_facts("g) Total Expenses & Profit 41.9%")
    profit_facts = [f for f in facts if f.fact_type == "profit_provision"]
    assert not profit_facts, (
        f"'Total Expenses & Profit' must not yield a profit_provision; got {profit_facts}"
    )


def test_underwriting_profit_intentionally_not_captured_by_standalone_pattern() -> None:
    # TRADE-OFF (documented): a clean standalone "Underwriting Profit 9.0%" line IS a real
    # profit provision we would like to capture. However, the standalone "Profit" pattern
    # keeps a `(?<!\w\s)` guard that also blocks "Underwriting Profit". This guard is
    # load-bearing on the real Brazos/Accredited Exhibit R pages, where "Underwriting Profit"
    # also appears on lines we must NOT capture:
    #   - "Federal Income Tax on Underwriting Profit = (6) x 21%"  (21% is a tax rate)
    #   - "Underwriting Profit After Federal Income Tax ... 7.1%"  (after-tax, not the provision)
    # Dropping the guard to recall the clean case re-introduces those false positives across
    # attachment_8 / attachment_9, so we keep it. A missing fact is preferable to a wrong one;
    # the genuine pre-tax 9.0% provision is still captured via the "Profit Load" pattern.
    facts = extract_rate_facts("Underwriting Profit 9.0%")
    profit_facts = [f for f in facts if f.fact_type == "profit_provision"]
    assert not profit_facts, (
        "Standalone 'Profit' pattern intentionally does not fire on 'Underwriting Profit' "
        f"(see (?<!\\w\\s) guard rationale); got {profit_facts}"
    )


def test_exhibit_g_decimal_form_not_captured_as_permissible_loss_ratio() -> None:
    # "i) Permissible Loss & LAE Ratio in Decimal Form 0.581" has no %, must not fire
    facts = extract_rate_facts(_EXHIBIT_G_BLOCK)
    permissible = [f for f in facts if f.fact_type == "permissible_loss_ratio"]
    # There should be exactly one permissible_loss_ratio fact (58.1, not 0.581)
    assert len(permissible) == 1, (
        f"Expected exactly 1 permissible_loss_ratio fact (58.1%); got {[f.normalized_value for f in permissible]}"
    )


def test_expected_loss_ratio_standalone_fixture() -> None:
    facts = extract_rate_facts("Expected Loss Ratio 65.0%")
    elr = [f for f in facts if f.fact_type == "expected_loss_ratio"]
    assert elr, "Expected an expected_loss_ratio fact"
    assert elr[0].normalized_value == "65.0"
    assert elr[0].fact_key == "expected_loss_ratio"


def test_standalone_profit_provision_does_not_duplicate_with_existing_patterns() -> None:
    # "Selected underwriting profit provision 9.5%" produces EXACTLY 2 profit_provision
    # facts, and the new standalone "Profit" pattern must not add a 3rd.
    #
    # Pre-existing duplicate (NOT introduced by this task): two of the older
    # PERCENT_LABELS patterns both match this string —
    #   1. `selected\s+underwriting\s+profit\s+provision`  -> role "selected"
    #   2. the generic `profit\s+provision`                -> role "unknown"
    # So the baseline count is 2. The new standalone "Profit" pattern carries a
    # `(?!\s*(?:provision|load|margin))` lookahead precisely so it does NOT fire on
    # "profit provision" text and bump this to 3.
    facts = extract_rate_facts("Selected underwriting profit provision 9.5%")
    profit_facts = [f for f in facts if f.fact_type == "profit_provision"]
    # Must include the selected role
    selected = [f for f in profit_facts if f.role == "selected"]
    assert selected, "Must have a profit_provision with role 'selected'"
    assert selected[0].normalized_value == "9.5"
    # Exactly the pre-existing 2 — the standalone pattern must not add a 3rd.
    assert len(profit_facts) == 2, (
        "Expected exactly 2 pre-existing profit_provision facts; the new standalone "
        f"Profit pattern must not add another. Got {len(profit_facts)}: "
        f"{[(f.role, f.normalized_value) for f in profit_facts]}"
    )
