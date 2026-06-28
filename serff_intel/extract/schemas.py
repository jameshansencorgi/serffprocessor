from __future__ import annotations

from pydantic import BaseModel, Field


class EvidenceFact(BaseModel):
    fact_type: str
    fact_key: str | None = None
    fact_value: str
    normalized_value: str | None = None
    unit: str | None = None
    coverage: str | None = None
    role: str | None = None
    scope: str | None = None
    territory: str | None = None
    confidence: float = Field(ge=0, le=1)
    needs_review: bool = False
    review_reason: str | None = None
    evidence_text: str
    page_number: int | None = None
    table_id: int | None = None
    table_cell_id: int | None = None
    table_name: str | None = None
    table_kind: str | None = None
    row_label: str | None = None
    row_key: str | None = None
    col_label: str | None = None
    col_key: str | None = None
    cell_address: str | None = None
    table_locator_text: str | None = None
    effective_start_date: str | None = None
    effective_end_date: str | None = None
    snapshot_filing_id: int | None = None
    supersedes_fact_id: int | None = None
    superseded_by_fact_id: int | None = None
    supersession_status: str = "active"
    extraction_method: str = "regex"
