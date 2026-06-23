from __future__ import annotations

from pydantic import BaseModel, Field


class EvidenceFact(BaseModel):
    fact_type: str
    fact_value: str
    normalized_value: str | None = None
    confidence: float = Field(ge=0, le=1)
    evidence_text: str
    page_number: int | None = None
    extraction_method: str = "regex"

