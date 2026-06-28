from __future__ import annotations

import csv
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from serff_intel import dtos
from serff_intel.models import (
    Attachment,
    AttachmentParseDecision,
    ExtractedFact,
    ExtractedTable,
    ExtractedTableCell,
    Filing,
    FilingSegment,
    HarmonizedFiling,
)

RATE_CHANGE_FACTS = {"requested_rate_change", "approved_rate_change", "indicated_rate_level_change", "selected_rate_level_change"}
LCM_FACTS = {"loss_cost_multiplier"}
PROVISION_FACTS = {"expense_provision", "profit_provision", "loss_trend"}
WRITTEN_PREMIUM_FACTS = {"written_premium_impact"}
OBJECTION_FACTS = {"regulator_objection"}


def rate_gap(requested: float | None, approved: float | None) -> float | None:
    """Requested-minus-approved overall rate change; ``None`` unless both are present."""
    if requested is None or approved is None:
        return None
    return round(requested - approved, 4)


def export_actuarial_tables(session: Session, out_dir: Path) -> dtos.ExportResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    exports = {
        "filings.csv": _filing_rows(session),
        "attachments.csv": _attachment_rows(session),
        "rate_changes.csv": _fact_rows(session, RATE_CHANGE_FACTS),
        "loss_cost_multipliers.csv": _fact_rows(session, LCM_FACTS),
        "provisions.csv": _fact_rows(session, PROVISION_FACTS),
        "written_premium_impacts.csv": _fact_rows(session, WRITTEN_PREMIUM_FACTS),
        "objections.csv": _fact_rows(session, OBJECTION_FACTS),
        "segments.csv": _segment_rows(session),
        "extracted_tables.csv": _table_rows(session),
        "extracted_table_cells.csv": _table_cell_rows(session),
        "harmonized_filings.csv": _harmonized_rows(session),
    }
    rows_written = 0
    files_written = 0
    for filename, rows in exports.items():
        _write_csv(out_dir / filename, rows)
        files_written += 1
        rows_written += len(rows)
    return dtos.ExportResult(files_written=files_written, rows_written=rows_written)


def export_review_csv(
    session: Session,
    output_path: Path,
    limit: int | None = None,
    *,
    include_all: bool = False,
) -> dtos.ExportResult:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = _review_rows(session, limit, include_all=include_all)
    _write_csv(output_path, rows)
    return dtos.ExportResult(files_written=1, rows_written=len(rows))


def _filing_rows(session: Session) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for filing in session.scalars(select(Filing).order_by(Filing.state, Filing.serff_tracking_number)):
        rows.append(
            {
                "filing_id": filing.id,
                "serff_tracking_number": filing.serff_tracking_number,
                "state": filing.state,
                "company_name": filing.company_name,
                "naic_company_code": filing.naic_company_code,
                "line_of_business": filing.line_of_business,
                "sub_type": filing.sub_type,
                "filing_type": filing.filing_type,
                "status": filing.status,
                "submitted_date": filing.submitted_date,
                "disposition_date": filing.disposition_date,
                "effective_date": filing.effective_date,
                "rate_impact_requested": filing.rate_impact_requested,
                "rate_impact_approved": filing.rate_impact_approved,
                "requested_approved_rate_gap": rate_gap(filing.rate_impact_requested, filing.rate_impact_approved),
            }
        )
    return rows


def _attachment_rows(session: Session) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    query = (
        select(Attachment, Filing, AttachmentParseDecision)
        .join(Filing, Filing.id == Attachment.filing_id)
        .join(AttachmentParseDecision, AttachmentParseDecision.attachment_id == Attachment.id, isouter=True)
        .order_by(Filing.state, Filing.serff_tracking_number, Attachment.filename)
    )
    for attachment, filing, decision in session.execute(query):
        rows.append(
            {
                "attachment_id": attachment.id,
                "filing_id": filing.id,
                "serff_tracking_number": filing.serff_tracking_number,
                "state": filing.state,
                "company_name": filing.company_name,
                "filename": attachment.filename,
                "file_type": attachment.file_type,
                "document_class": attachment.document_class,
                "page_count": attachment.page_count,
                "parse_status": attachment.parse_status,
                "extraction_route": decision.extraction_route if decision else "",
                "value_tier": decision.value_tier if decision else "",
                "ocr_needed": decision.ocr_needed if decision else "",
                "ocr_used": decision.ocr_used if decision else attachment.ocr_used,
                "native_text_chars": decision.native_text_chars if decision else "",
                "table_like_score": decision.table_like_score if decision else "",
                "route_reason": decision.route_reason if decision else "",
                "sha256": attachment.sha256,
                "local_path": attachment.local_path,
            }
        )
    return rows


def _fact_rows(session: Session, fact_types: set[str]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    query = (
        select(ExtractedFact, Filing, Attachment)
        .join(Filing, Filing.id == ExtractedFact.filing_id)
        .join(Attachment, Attachment.id == ExtractedFact.attachment_id, isouter=True)
        .where(ExtractedFact.fact_type.in_(fact_types))
        .order_by(Filing.state, Filing.serff_tracking_number, ExtractedFact.fact_type, ExtractedFact.id)
    )
    for fact, filing, attachment in session.execute(query):
        rows.append(_fact_row(fact, filing, attachment))
    return rows


def _review_rows(session: Session, limit: int | None, *, include_all: bool) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    query = (
        select(ExtractedFact, Filing, Attachment)
        .join(Filing, Filing.id == ExtractedFact.filing_id)
        .join(Attachment, Attachment.id == ExtractedFact.attachment_id, isouter=True)
        .order_by(
            ExtractedFact.needs_review.desc(),
            ExtractedFact.confidence,
            Filing.state,
            Filing.serff_tracking_number,
            ExtractedFact.id,
        )
    )
    if not include_all:
        query = query.where(ExtractedFact.needs_review.is_(True))
    if limit:
        query = query.limit(limit)
    for fact, filing, attachment in session.execute(query):
        row = _fact_row(fact, filing, attachment)
        row.update({"accepted": "", "corrected_value": "", "notes": ""})
        rows.append(row)
    return rows


def _fact_row(fact: ExtractedFact, filing: Filing, attachment: Attachment | None) -> dict[str, object]:
    return {
        "fact_id": fact.id,
        "filing_id": filing.id,
        "attachment_id": attachment.id if attachment else "",
        "serff_tracking_number": filing.serff_tracking_number,
        "state": filing.state,
        "company_name": filing.company_name,
        "line_of_business": filing.line_of_business,
        "filename": attachment.filename if attachment else "",
        "document_class": attachment.document_class if attachment else "",
        "fact_type": fact.fact_type,
        "fact_key": fact.fact_key,
        "fact_value": fact.fact_value,
        "normalized_value": fact.normalized_value,
        "unit": fact.unit,
        "coverage": fact.coverage,
        "role": fact.role,
        "scope": fact.scope,
        "territory": fact.territory,
        "confidence": fact.confidence,
        "needs_review": fact.needs_review,
        "review_reason": fact.review_reason,
        "page_number": fact.page_number,
        "table_id": fact.table_id,
        "table_cell_id": fact.table_cell_id,
        "table_name": fact.table_name,
        "table_kind": fact.table_kind,
        "row_label": fact.row_label,
        "col_label": fact.col_label,
        "cell_address": fact.cell_address,
        "effective_start_date": fact.effective_start_date,
        "effective_end_date": fact.effective_end_date,
        "snapshot_filing_id": fact.snapshot_filing_id,
        "supersession_status": fact.supersession_status,
        "evidence_text": fact.evidence_text,
        "extraction_method": fact.extraction_method,
    }


def _segment_rows(session: Session) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    query = (
        select(FilingSegment, Filing, Attachment)
        .join(Filing, Filing.id == FilingSegment.filing_id)
        .join(Attachment, Attachment.id == FilingSegment.attachment_id, isouter=True)
        .order_by(Filing.state, Filing.serff_tracking_number, FilingSegment.id)
    )
    for segment, filing, attachment in session.execute(query):
        rows.append(
            {
                "segment_id": segment.id,
                "filing_id": filing.id,
                "attachment_id": attachment.id if attachment else "",
                "serff_tracking_number": filing.serff_tracking_number,
                "state": filing.state,
                "company_name": filing.company_name,
                "filename": attachment.filename if attachment else "",
                "segment_index": segment.segment_index,
                "page_start": segment.page_start,
                "page_end": segment.page_end,
                "is_substantive": segment.is_substantive,
                "function_label": segment.function_label,
                "topic_label": segment.topic_label,
                "classifier_version": segment.classifier_version,
                "segment_text": segment.segment_text,
            }
        )
    return rows


def _harmonized_rows(session: Session) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    query = (
        select(HarmonizedFiling, Filing)
        .join(Filing, Filing.id == HarmonizedFiling.filing_id)
        .order_by(HarmonizedFiling.state, HarmonizedFiling.line_of_business, HarmonizedFiling.company_name)
    )
    for harmonized, filing in session.execute(query):
        rows.append(
            {
                "release_id": harmonized.release_id,
                "filing_id": harmonized.filing_id,
                "serff_tracking_number": filing.serff_tracking_number,
                "state": harmonized.state,
                "line_of_business": harmonized.line_of_business,
                "company_name": harmonized.company_name,
                "selection_rank": harmonized.selection_rank,
                "selection_score": harmonized.selection_score,
                "selection_reason": harmonized.selection_reason,
                "page_count": harmonized.page_count,
                "attachment_count": harmonized.attachment_count,
                "fact_count": harmonized.fact_count,
                "segment_count": harmonized.segment_count,
            }
        )
    return rows


def _table_rows(session: Session) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    query = (
        select(ExtractedTable, Filing, Attachment)
        .join(Filing, Filing.id == ExtractedTable.filing_id)
        .join(Attachment, Attachment.id == ExtractedTable.attachment_id)
        .order_by(Filing.state, Filing.serff_tracking_number, ExtractedTable.id)
    )
    for table, filing, attachment in session.execute(query):
        rows.append(
            {
                "table_id": table.id,
                "filing_id": filing.id,
                "attachment_id": attachment.id,
                "serff_tracking_number": filing.serff_tracking_number,
                "state": filing.state,
                "company_name": filing.company_name,
                "filename": attachment.filename,
                "page_number": table.page_number,
                "table_index": table.table_index,
                "table_name": table.table_name,
                "table_kind": table.table_kind,
                "confidence": table.confidence,
                "needs_review": table.needs_review,
                "locator_text": table.locator_text,
            }
        )
    return rows


def _table_cell_rows(session: Session) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    query = (
        select(ExtractedTableCell, ExtractedTable, Filing, Attachment)
        .join(ExtractedTable, ExtractedTable.id == ExtractedTableCell.table_id)
        .join(Filing, Filing.id == ExtractedTable.filing_id)
        .join(Attachment, Attachment.id == ExtractedTable.attachment_id)
        .order_by(Filing.state, Filing.serff_tracking_number, ExtractedTableCell.id)
    )
    for cell, table, filing, attachment in session.execute(query):
        rows.append(
            {
                "table_cell_id": cell.id,
                "table_id": table.id,
                "filing_id": filing.id,
                "attachment_id": attachment.id,
                "serff_tracking_number": filing.serff_tracking_number,
                "state": filing.state,
                "company_name": filing.company_name,
                "filename": attachment.filename,
                "page_number": table.page_number,
                "table_kind": table.table_kind,
                "row_index": cell.row_index,
                "col_index": cell.col_index,
                "row_label": cell.row_label,
                "row_key": cell.row_key,
                "col_label": cell.col_label,
                "col_key": cell.col_key,
                "cell_address": cell.cell_address,
                "raw_value": cell.raw_value,
                "normalized_value": cell.normalized_value,
                "confidence": cell.confidence,
                "needs_review": cell.needs_review,
            }
        )
    return rows


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames = list(rows[0].keys()) if rows else ["empty"]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
