"""Controlled vocabularies shared between extraction and persistence.

These are the single source of truth for enum-like fields so that the extractor
(Path 1) and the database/validation layer (Path 2) cannot drift apart. Keep them
in sync with ``docs/fact_catalogue.yml`` ``role_enum`` (additive only).
"""

from __future__ import annotations

# Roles a fact can carry; mirrors rate_impact._role_from_context outputs.
ROLES: frozenset[str] = frozenset(
    {
        "unknown",
        "prior",
        "indicated",
        "selected",
        "rounded",
        "offset",
        "approved",
        "requested",
        "filed",
        "final",
    }
)

# Units a normalized value can be expressed in.
UNITS: frozenset[str] = frozenset(
    {"percent", "dollars", "factor", "rate", "count", "text", "code", "date", "composite"}
)

SUPERSESSION_STATUSES: frozenset[str] = frozenset({"active", "superseded"})

# Table classifications produced by tables._infer_table_kind.
TABLE_KINDS: frozenset[str] = frozenset(
    {
        "lcm_support",
        "profit_support",
        "expense_support",
        "trend_support",
        "rating_factor_grid",
        "rate_impact",
        "unknown",
    }
)

EXTRACTION_METHODS: frozenset[str] = frozenset(
    {
        "regex:rate_impact",
        "keyword:actuarial_reasons",
        "regex:objections",
        "filename_inference",
        "table_parser",
        "manual_review",
    }
)

# Why a fact was flagged for human review.
REVIEW_REASONS: frozenset[str] = frozenset(
    {
        "ambiguous_role",
        "ambiguous_percent_candidates",
        "distractor_number",
        "no_coverage",
        "keyword_only",
        "low_confidence_table",
        # Set by the pipeline when a fact_type has no catalogue key (Path 2 / pipeline.py).
        "unknown_fact_key",
    }
)

# Regulator-objection topics (classify_objection_topic output).
OBJECTION_TOPICS: frozenset[str] = frozenset(
    {
        "trend",
        "credibility",
        "expense",
        "profit",
        "rate_level",
        "catastrophe",
        "data_quality",
        "reinsurance",
        "general",
    }
)

# Normalized filing disposition vocabulary (normalize_disposition output).
DISPOSITIONS: frozenset[str] = frozenset(
    {"approved", "withdrawn", "disapproved", "filed_and_used", "closed", "pending"}
)
