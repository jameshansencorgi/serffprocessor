from __future__ import annotations

import hashlib
from pathlib import Path
import traceback
from uuid import uuid4

from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.orm import Session

from serff_intel import dtos
from serff_intel.classify.document_classifier import classify_document
from serff_intel.classify.segment_classifier import classify_segment
from serff_intel.config import Settings
from serff_intel.extract.actuarial_reasons import extract_reason_facts
from serff_intel.extract.context import infer_coverage
from serff_intel.extract.entities import extract_metadata_from_text
from serff_intel.extract.fact_keys import canonical_fact_key
from serff_intel.extract.objections import extract_objection_facts
from serff_intel.extract.rate_impact import extract_rate_facts
from serff_intel.extract.tables import cell_address, cell_labels, extract_table_candidates
from serff_intel.models import (
    Attachment,
    AttachmentParseDecision,
    DocumentPage,
    EmbeddingChunk,
    ExtractedTable,
    ExtractedTableCell,
    ExtractedFact,
    Filing,
    FilingSegment,
    ProcessingError,
    RegulatorObjection,
    utc_now,
)
from serff_intel.parsing.router import decide_parse_route
from serff_intel.parsing.text_extract import parse_document


def process_pending(
    session: Session,
    settings: Settings,
    *,
    limit: int | None = None,
    serff: str | None = None,
    dry_run: bool = False,
    fail_fast: bool = False,
    retry_failed: bool = False,
    max_retries: int = 3,
) -> dtos.ProcessingResult:
    attachments_processed = 0
    pages_created = 0
    segments_created = 0
    facts_created = 0
    chunks_created = 0
    run_id = uuid4().hex
    query = (
        select(Attachment)
        .join(Filing, Filing.id == Attachment.filing_id)
        .where(Attachment.terminal_failed.is_(False))
        .order_by(Attachment.id)
    )
    if retry_failed:
        query = query.where(
            or_(
                Attachment.parse_status == "pending",
                (Attachment.parse_status == "failed") & (Attachment.retry_count < max_retries),
            )
        )
    else:
        query = query.where(Attachment.parse_status == "pending")
    if serff:
        query = query.where(Filing.serff_tracking_number == serff)
    if limit is not None:
        query = query.limit(limit)
    attachments = session.scalars(query).all()
    if dry_run:
        return dtos.ProcessingResult(
            attachments_processed=len(attachments),
            pages_created=0,
            segments_created=0,
            facts_created=0,
            chunks_created=0,
        )
    settings.text_dir.mkdir(parents=True, exist_ok=True)
    for attachment in attachments:
        stage = "parse"
        try:
            attachments_processed += 1
            parsed = parse_document(Path(attachment.local_path))
            stage = "clear_previous_results"
            _clear_attachment_outputs(session, attachment.id)
            session.commit()

            stage = "persist_pages"
            for page in parsed.pages:
                session.add(
                    DocumentPage(
                        attachment_id=attachment.id,
                        page_number=page.page_number,
                        text=page.text,
                        ocr_confidence=None,
                        layout_json=None,
                    )
                )
            session.commit()
            pages_created += _count_attachment_rows(session, DocumentPage, attachment.id)

            full_text = "\n\n".join(page.text for page in parsed.pages)
            stage = "classify"
            classification = classify_document(attachment.filename, full_text)
            attachment.document_class = classification.document_class
            attachment.page_count = len(parsed.pages)
            attachment.ocr_used = any(page.ocr_used for page in parsed.pages)
            attachment.parse_status = "parsed" if parsed.pages and not parsed.failures else "failed"
            attachment.retry_count = 0
            attachment.last_error_stage = None
            attachment.last_error_at = None
            attachment.terminal_failed = False
            decision = decide_parse_route(
                file_type=attachment.file_type,
                pages=parsed.pages,
                document_class=classification.document_class,
                failures=parsed.failures,
            )
            session.add(
                AttachmentParseDecision(
                    attachment_id=attachment.id,
                    document_class=decision.document_class,
                    extraction_route=decision.extraction_route,
                    value_tier=decision.value_tier,
                    native_text_chars=decision.native_text_chars,
                    page_count=decision.page_count,
                    table_like_score=decision.table_like_score,
                    ocr_needed=decision.ocr_needed,
                    ocr_used=decision.ocr_used,
                    route_reason=decision.route_reason,
                )
            )
            text_path = settings.text_dir / f"attachment_{attachment.id}.txt"
            text_path.write_text(full_text)
            attachment.parsed_text_path = str(text_path)
            _backfill_filing_metadata(session, attachment, full_text)
            session.commit()

            stage = "extract"
            facts_before = _count_attachment_rows(session, ExtractedFact, attachment.id)
            for page in parsed.pages:
                facts = []
                facts.extend(extract_rate_facts(page.text, page.page_number))
                facts.extend(extract_reason_facts(page.text, page.page_number))
                facts.extend(extract_objection_facts(page.text, page.page_number))
                _persist_tables(session, attachment, page.page_number, page.text)
                inferred_coverage = infer_coverage(attachment.filename, page.text)
                for fact in facts:
                    coverage = fact.coverage or inferred_coverage
                    fact_key = getattr(fact, "fact_key", None) or canonical_fact_key(fact.fact_type) or "unknown"
                    needs_review = fact.needs_review or fact_key == "unknown"
                    review_reason = getattr(fact, "review_reason", None)
                    if needs_review and review_reason is None and fact_key == "unknown":
                        review_reason = "unknown_fact_key"
                    session.add(
                        ExtractedFact(
                            filing_id=attachment.filing_id,
                            attachment_id=attachment.id,
                            fact_type=fact.fact_type,
                            fact_key=fact_key,
                            fact_value=fact.fact_value,
                            normalized_value=fact.normalized_value,
                            unit=fact.unit,
                            coverage=coverage,
                            role=fact.role,
                            scope=fact.scope,
                            territory=fact.territory,
                            confidence=fact.confidence,
                            needs_review=needs_review,
                            review_reason=review_reason,
                            evidence_text=fact.evidence_text,
                            page_number=fact.page_number,
                            table_id=fact.table_id,
                            table_cell_id=fact.table_cell_id,
                            table_name=fact.table_name,
                            table_kind=fact.table_kind,
                            row_label=fact.row_label,
                            row_key=fact.row_key,
                            col_label=fact.col_label,
                            col_key=fact.col_key,
                            cell_address=fact.cell_address,
                            table_locator_text=fact.table_locator_text,
                            effective_start_date=None,
                            effective_end_date=None,
                            snapshot_filing_id=attachment.filing_id,
                            supersedes_fact_id=fact.supersedes_fact_id,
                            superseded_by_fact_id=fact.superseded_by_fact_id,
                            supersession_status=fact.supersession_status,
                            extraction_method=fact.extraction_method,
                        )
                    )
                    if fact.fact_type == "regulator_objection":
                        session.add(
                            RegulatorObjection(
                                filing_id=attachment.filing_id,
                                attachment_id=attachment.id,
                                topic="general",
                                objection_text=fact.fact_value,
                                resolved_bool=False,
                                evidence_text=fact.evidence_text,
                            )
                        )
            session.commit()
            facts_created += _count_attachment_rows(session, ExtractedFact, attachment.id) - facts_before

            stage = "chunk"
            segments_before = _count_attachment_rows(session, FilingSegment, attachment.id)
            chunks_before = _count_attachment_rows(session, EmbeddingChunk, attachment.id)
            for page in parsed.pages:
                for chunk_index, chunk in enumerate(chunk_text(page.text), start=1):
                    segment_classification = classify_segment(chunk)
                    session.add(
                        FilingSegment(
                            filing_id=attachment.filing_id,
                            attachment_id=attachment.id,
                            segment_index=chunk_index,
                            segment_text=chunk,
                            page_start=page.page_number,
                            page_end=page.page_number,
                            is_substantive=segment_classification.is_substantive,
                            function_label=segment_classification.function_label,
                            topic_label=segment_classification.topic_label,
                        )
                    )
                    session.add(
                        EmbeddingChunk(
                            filing_id=attachment.filing_id,
                            attachment_id=attachment.id,
                            page_number=page.page_number,
                            chunk_text=chunk,
                            chunk_type="text",
                        )
                    )
            session.commit()
            segments_created += _count_attachment_rows(session, FilingSegment, attachment.id) - segments_before
            chunks_created += _count_attachment_rows(session, EmbeddingChunk, attachment.id) - chunks_before
        except Exception as exc:
            session.rollback()
            _record_processing_error(session, run_id, attachment, stage, exc, max_retries=max_retries)
            if fail_fast:
                raise
            continue
    rebuild_fts(session)
    return dtos.ProcessingResult(
        attachments_processed=attachments_processed,
        pages_created=pages_created,
        segments_created=segments_created,
        facts_created=facts_created,
        chunks_created=chunks_created,
    )


def _clear_attachment_outputs(session: Session, attachment_id: int) -> None:
    session.execute(delete(DocumentPage).where(DocumentPage.attachment_id == attachment_id))
    session.execute(delete(ExtractedFact).where(ExtractedFact.attachment_id == attachment_id))
    table_ids = session.scalars(select(ExtractedTable.id).where(ExtractedTable.attachment_id == attachment_id)).all()
    if table_ids:
        session.execute(delete(ExtractedTableCell).where(ExtractedTableCell.table_id.in_(table_ids)))
    session.execute(delete(ExtractedTable).where(ExtractedTable.attachment_id == attachment_id))
    session.execute(delete(EmbeddingChunk).where(EmbeddingChunk.attachment_id == attachment_id))
    session.execute(delete(FilingSegment).where(FilingSegment.attachment_id == attachment_id))
    session.execute(delete(AttachmentParseDecision).where(AttachmentParseDecision.attachment_id == attachment_id))
    session.execute(delete(RegulatorObjection).where(RegulatorObjection.attachment_id == attachment_id))


def _count_attachment_rows(session: Session, model: type, attachment_id: int) -> int:
    return session.scalar(select(func.count(model.id)).where(model.attachment_id == attachment_id)) or 0


def rebuild_fts(session: Session) -> int:
    session.execute(text("DELETE FROM filing_fts"))
    pages = session.execute(
        select(DocumentPage, Attachment.filing_id).join(Attachment, Attachment.id == DocumentPage.attachment_id)
    ).all()
    for page, filing_id in pages:
        session.execute(
            text("INSERT INTO filing_fts(filing_id, attachment_id, page_number, text) VALUES (:f, :a, :p, :t)"),
            {"f": filing_id, "a": page.attachment_id, "p": page.page_number, "t": page.text},
        )
    session.commit()
    return len(pages)


def chunk_text(text_value: str, max_chars: int = 1400, overlap: int = 180) -> list[str]:
    text_value = " ".join(text_value.split())
    if not text_value:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text_value):
        end = min(len(text_value), start + max_chars)
        chunks.append(text_value[start:end])
        if end == len(text_value):
            break
        start = max(0, end - overlap)
    return chunks


def _persist_tables(session: Session, attachment: Attachment, page_number: int, text_value: str) -> None:
    for candidate in extract_table_candidates(text_value):
        table = ExtractedTable(
            filing_id=attachment.filing_id,
            attachment_id=attachment.id,
            page_number=page_number,
            table_index=candidate.table_index,
            table_name=candidate.table_name,
            table_kind=candidate.table_kind,
            confidence=candidate.confidence,
            needs_review=candidate.needs_review,
            locator_text=candidate.locator_text,
        )
        session.add(table)
        session.flush()
        for row_index, row in enumerate(candidate.rows, start=1):
            for col_index, raw_value in enumerate(row, start=1):
                row_label, row_key, col_label, col_key = cell_labels(candidate.rows, row_index, col_index)
                session.add(
                    ExtractedTableCell(
                        table_id=table.id,
                        row_index=row_index,
                        col_index=col_index,
                        row_label=row_label,
                        row_key=row_key,
                        col_label=col_label,
                        col_key=col_key,
                        cell_address=cell_address(row_index, col_index),
                        raw_value=raw_value,
                        normalized_value=raw_value.replace(",", "").replace("$", "").replace("%", ""),
                        confidence=candidate.confidence,
                        needs_review=candidate.needs_review,
                    )
                )


def _record_processing_error(
    session: Session,
    run_id: str,
    attachment: Attachment,
    stage: str,
    exc: Exception,
    *,
    max_retries: int,
) -> None:
    formatted = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    current_attachment = session.get(Attachment, attachment.id)
    retry_count = 0
    terminal_failed = False
    if current_attachment is not None:
        current_attachment.parse_status = "failed"
        current_attachment.retry_count = (current_attachment.retry_count or 0) + 1
        current_attachment.last_error_stage = stage
        current_attachment.last_error_at = utc_now()
        current_attachment.terminal_failed = current_attachment.retry_count >= max_retries
        retry_count = current_attachment.retry_count
        terminal_failed = current_attachment.terminal_failed
    session.add(
        ProcessingError(
            run_id=run_id,
            filing_id=attachment.filing_id,
            attachment_id=attachment.id,
            stage=stage,
            exception_type=type(exc).__name__,
            message=str(exc),
            traceback_hash=hashlib.sha256(formatted.encode("utf-8")).hexdigest(),
            retryable=not terminal_failed and retry_count < max_retries,
        )
    )
    session.commit()


def _backfill_filing_metadata(session: Session, attachment: Attachment, text_value: str) -> None:
    filing = session.get(Filing, attachment.filing_id)
    if not filing:
        return
    metadata = extract_metadata_from_text(text_value)
    if metadata.get("company_name") and not filing.company_name:
        filing.company_name = metadata["company_name"]
    if metadata.get("naic_company_code") and not filing.naic_company_code:
        filing.naic_company_code = metadata["naic_company_code"]
