"""Canonical mapping from extractor ``fact_type`` strings to ``fact_catalogue.yml`` keys.

The extractors emit operational ``fact_type`` values (e.g. ``requested_rate_change``)
while the catalogue is keyed by ``fact_key`` (e.g. ``requested_overall_rate_change``).
This map is the single bridge so stored facts can be joined back to the catalogue.

Every value here must exist as a key in ``docs/fact_catalogue.yml``; a conformance
test enforces that. A ``fact_type`` with no catalogue home (e.g. the aggregate
``expense_provision``) is intentionally absent and resolves to ``None``.
"""

from __future__ import annotations

CANONICAL_FACT_KEY: dict[str, str] = {
    # rate change family
    "requested_rate_change": "requested_overall_rate_change",
    "approved_rate_change": "approved_overall_rate_change",
    "indicated_rate_level_change": "indicated_rate_change",
    "selected_rate_level_change": "selected_rate_change",
    "written_premium_impact": "written_premium_impact",
    # rating foundation / provisions
    "loss_cost_multiplier": "loss_cost_multiplier",
    "loss_trend": "loss_trend",
    "profit_provision": "profit_provision",
    # ratemaking assumptions (numeric)
    "frequency_trend": "frequency_trend",
    "severity_trend": "severity_trend",
    "credibility": "credibility",
    # narrative keyword tags
    "social_inflation": "narrative_driver_tag",
    "nuclear_verdicts": "narrative_driver_tag",
    "litigation": "narrative_driver_tag",
    "telematics": "narrative_driver_tag",
    "new_ventures": "narrative_driver_tag",
    "trucking": "narrative_driver_tag",
    # regulator interaction
    "regulator_objection": "regulator_objection",
    # expense / profit / permissible-loss ratio (Exhibit E/G)
    "commission_expense_ratio": "commission_expense_ratio",
    "other_acquisition_expense_ratio": "other_acquisition_expense_ratio",
    "general_expense_ratio": "general_expense_ratio",
    "taxes_licenses_fees_ratio": "taxes_licenses_fees_ratio",
    "permissible_loss_ratio": "permissible_loss_ratio",
    "expected_loss_ratio": "expected_loss_ratio",
}


def canonical_fact_key(fact_type: str) -> str | None:
    """Return the catalogue ``fact_key`` for an extractor ``fact_type``, or ``None``."""
    return CANONICAL_FACT_KEY.get(fact_type)
