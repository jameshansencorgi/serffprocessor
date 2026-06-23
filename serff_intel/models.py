from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class RawS3Object(Base):
    __tablename__ = "raw_s3_object"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bucket: Mapped[Optional[str]] = mapped_column(String(255))
    key: Mapped[Optional[str]] = mapped_column(Text)
    etag: Mapped[Optional[str]] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    content_type: Mapped[Optional[str]] = mapped_column(String(255))
    last_modified: Mapped[Optional[datetime]] = mapped_column(DateTime)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    local_cache_path: Mapped[str] = mapped_column(Text)
    raw_metadata_json: Mapped[Optional[str]] = mapped_column(Text)


class RawFilingBundle(Base):
    __tablename__ = "raw_filing_bundle"
    __table_args__ = (UniqueConstraint("state", "serff_tracking_number", name="uq_bundle_state_serff"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    state: Mapped[str] = mapped_column(String(8), index=True)
    serff_tracking_number: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(64), default="manual")
    s3_prefix: Mapped[Optional[str]] = mapped_column(Text)
    discovered_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    coverage_status: Mapped[str] = mapped_column(String(64), default="discovered")
    raw_metadata_json: Mapped[Optional[str]] = mapped_column(Text)

    filings: Mapped[list["Filing"]] = relationship(back_populates="raw_bundle")


class Filing(Base):
    __tablename__ = "filing"
    __table_args__ = (UniqueConstraint("state", "serff_tracking_number", name="uq_filing_state_serff"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    raw_bundle_id: Mapped[Optional[int]] = mapped_column(ForeignKey("raw_filing_bundle.id"))
    serff_tracking_number: Mapped[str] = mapped_column(String(64), index=True)
    state: Mapped[str] = mapped_column(String(8), index=True)
    insurance_type: Mapped[Optional[str]] = mapped_column(String(255))
    sub_type: Mapped[Optional[str]] = mapped_column(String(255))
    line_of_business: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    company_name: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    naic_company_code: Mapped[Optional[str]] = mapped_column(String(32))
    group_name: Mapped[Optional[str]] = mapped_column(String(255))
    filing_type: Mapped[Optional[str]] = mapped_column(String(255))
    status: Mapped[Optional[str]] = mapped_column(String(128))
    submitted_date: Mapped[Optional[datetime]] = mapped_column(Date)
    disposition_date: Mapped[Optional[datetime]] = mapped_column(Date)
    effective_date: Mapped[Optional[datetime]] = mapped_column(Date)
    rate_impact_requested: Mapped[Optional[float]] = mapped_column(Float)
    rate_impact_approved: Mapped[Optional[float]] = mapped_column(Float)
    source_url: Mapped[Optional[str]] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0.6)
    raw_metadata_json: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    raw_bundle: Mapped[Optional[RawFilingBundle]] = relationship(back_populates="filings")
    attachments: Mapped[list["Attachment"]] = relationship(back_populates="filing", cascade="all, delete-orphan")


class Attachment(Base):
    __tablename__ = "attachment"
    __table_args__ = (UniqueConstraint("filing_id", "sha256", name="uq_attachment_filing_sha"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filing_id: Mapped[int] = mapped_column(ForeignKey("filing.id"), index=True)
    raw_s3_object_id: Mapped[Optional[int]] = mapped_column(ForeignKey("raw_s3_object.id"))
    filename: Mapped[str] = mapped_column(String(512))
    file_type: Mapped[str] = mapped_column(String(64))
    local_path: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    page_count: Mapped[Optional[int]] = mapped_column(Integer)
    document_class: Mapped[Optional[str]] = mapped_column(String(128), index=True)
    ocr_used: Mapped[bool] = mapped_column(Boolean, default=False)
    parsed_text_path: Mapped[Optional[str]] = mapped_column(Text)
    parse_status: Mapped[str] = mapped_column(String(64), default="pending")
    raw_metadata_json: Mapped[Optional[str]] = mapped_column(Text)

    filing: Mapped[Filing] = relationship(back_populates="attachments")


class DocumentPage(Base):
    __tablename__ = "document_page"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attachment_id: Mapped[int] = mapped_column(ForeignKey("attachment.id"), index=True)
    page_number: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    ocr_confidence: Mapped[Optional[float]] = mapped_column(Float)
    layout_json: Mapped[Optional[str]] = mapped_column(Text)


class ExtractedFact(Base):
    __tablename__ = "extracted_fact"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filing_id: Mapped[int] = mapped_column(ForeignKey("filing.id"), index=True)
    attachment_id: Mapped[Optional[int]] = mapped_column(ForeignKey("attachment.id"), index=True)
    fact_type: Mapped[str] = mapped_column(String(128), index=True)
    fact_value: Mapped[str] = mapped_column(Text)
    normalized_value: Mapped[Optional[str]] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    evidence_text: Mapped[str] = mapped_column(Text)
    page_number: Mapped[Optional[int]] = mapped_column(Integer)
    bbox_json: Mapped[Optional[str]] = mapped_column(Text)
    extraction_method: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class RegulatorObjection(Base):
    __tablename__ = "regulator_objection"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filing_id: Mapped[int] = mapped_column(ForeignKey("filing.id"), index=True)
    attachment_id: Mapped[Optional[int]] = mapped_column(ForeignKey("attachment.id"))
    date: Mapped[Optional[datetime]] = mapped_column(Date)
    topic: Mapped[Optional[str]] = mapped_column(String(255))
    objection_text: Mapped[str] = mapped_column(Text)
    company_response_text: Mapped[Optional[str]] = mapped_column(Text)
    resolved_bool: Mapped[bool] = mapped_column(Boolean, default=False)
    evidence_text: Mapped[Optional[str]] = mapped_column(Text)


class EmbeddingChunk(Base):
    __tablename__ = "embedding_chunk"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filing_id: Mapped[int] = mapped_column(ForeignKey("filing.id"), index=True)
    attachment_id: Mapped[Optional[int]] = mapped_column(ForeignKey("attachment.id"), index=True)
    chunk_text: Mapped[str] = mapped_column(Text)
    page_number: Mapped[Optional[int]] = mapped_column(Integer)
    chunk_type: Mapped[str] = mapped_column(String(64), default="text")
    embedding_model: Mapped[Optional[str]] = mapped_column(String(255))
    embedding_vector_id: Mapped[Optional[str]] = mapped_column(String(255))


class FilingSegment(Base):
    __tablename__ = "filing_segment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filing_id: Mapped[int] = mapped_column(ForeignKey("filing.id"), index=True)
    attachment_id: Mapped[Optional[int]] = mapped_column(ForeignKey("attachment.id"), index=True)
    segment_index: Mapped[int] = mapped_column(Integer)
    segment_text: Mapped[str] = mapped_column(Text)
    page_start: Mapped[Optional[int]] = mapped_column(Integer)
    page_end: Mapped[Optional[int]] = mapped_column(Integer)
    is_substantive: Mapped[bool] = mapped_column(Boolean, default=True)
    function_label: Mapped[str] = mapped_column(String(128), default="unknown")
    topic_label: Mapped[str] = mapped_column(String(128), default="unknown")
    classifier_version: Mapped[str] = mapped_column(String(128), default="rules-v0.1")


class CorpusRelease(Base):
    __tablename__ = "corpus_release"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_corpus_release_name_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), default="SERFF-LOCUS")
    version: Mapped[str] = mapped_column(String(64), default="v0.1")
    description: Mapped[Optional[str]] = mapped_column(Text)
    selection_method: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    raw_metadata_json: Mapped[Optional[str]] = mapped_column(Text)


class HarmonizedFiling(Base):
    __tablename__ = "harmonized_filing"
    __table_args__ = (UniqueConstraint("release_id", "state", "line_of_business", "company_name", name="uq_harmonized_scope"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    release_id: Mapped[int] = mapped_column(ForeignKey("corpus_release.id"), index=True)
    filing_id: Mapped[int] = mapped_column(ForeignKey("filing.id"), index=True)
    state: Mapped[str] = mapped_column(String(8), index=True)
    line_of_business: Mapped[str] = mapped_column(String(255), index=True)
    company_name: Mapped[str] = mapped_column(String(255), index=True)
    selection_rank: Mapped[int] = mapped_column(Integer, default=1)
    selection_score: Mapped[float] = mapped_column(Float, default=0)
    selection_reason: Mapped[str] = mapped_column(Text)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    attachment_count: Mapped[int] = mapped_column(Integer, default=0)
    fact_count: Mapped[int] = mapped_column(Integer, default=0)
    segment_count: Mapped[int] = mapped_column(Integer, default=0)
    raw_metadata_json: Mapped[Optional[str]] = mapped_column(Text)


class CoverageSnapshot(Base):
    __tablename__ = "coverage_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    state: Mapped[str] = mapped_column(String(8), index=True)
    line_of_business: Mapped[Optional[str]] = mapped_column(String(255))
    date_range_start: Mapped[Optional[datetime]] = mapped_column(Date)
    date_range_end: Mapped[Optional[datetime]] = mapped_column(Date)
    filings_seen: Mapped[int] = mapped_column(Integer, default=0)
    filings_processed: Mapped[int] = mapped_column(Integer, default=0)
    attachments_processed: Mapped[int] = mapped_column(Integer, default=0)
    ocr_failure_count: Mapped[int] = mapped_column(Integer, default=0)
    parse_failure_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
