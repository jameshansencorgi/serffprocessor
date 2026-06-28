from __future__ import annotations

from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from serff_intel import dtos
from serff_intel.config import Settings
from serff_intel.export import export_actuarial_tables, export_review_csv
from serff_intel.ingest.comp_search import import_comp_search_run
from serff_intel.ingest.manual_import import discover_filing_folders, import_filing_folder, import_s3_manifest
from serff_intel.models import Attachment, CorpusRelease, ExtractedFact, Filing, FilingSegment, HarmonizedFiling
from serff_intel.pipeline import process_pending, rebuild_fts
from serff_intel.search.query import search


class FilingImportService:
    @staticmethod
    def import_folder(session: Session, folder: Path, state: str | None = None) -> Filing:
        return import_filing_folder(session, folder, default_state=state)

    @staticmethod
    def import_tree(session: Session, root_folder: Path) -> dtos.ImportTreeResult:
        folders = discover_filing_folders(root_folder)
        for folder in folders:
            import_filing_folder(session, folder)
        return dtos.ImportTreeResult(folders_seen=len(folders), filings_imported=len(folders))

    @staticmethod
    def import_manifest(session: Session, manifest_csv: Path) -> dtos.ManifestImportResult:
        return import_s3_manifest(session, manifest_csv)

    @staticmethod
    def import_comp_search_run(session: Session, results_json: Path) -> dtos.CompSearchImportResult:
        return import_comp_search_run(session, results_json)


class FilingProcessingService:
    @staticmethod
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
        return process_pending(
            session,
            settings,
            limit=limit,
            serff=serff,
            dry_run=dry_run,
            fail_fast=fail_fast,
            retry_failed=retry_failed,
            max_retries=max_retries,
        )

    @staticmethod
    def rebuild_search_index(session: Session) -> int:
        return rebuild_fts(session)


class CorpusReleaseService:
    @staticmethod
    def build_harmonized_release(
        session: Session,
        name: str = "SERFF-LOCUS",
        version: str = "v0.1",
    ) -> dtos.ReleaseBuildResult:
        release = session.scalar(
            select(CorpusRelease).where(CorpusRelease.name == name, CorpusRelease.version == version)
        )
        selection_method = (
            "For each (state, line_of_business, company_name) scope, select the processed filing "
            "with the highest score: parsed page count * 10 + extracted fact count + substantive segment count. "
            "This mirrors LOCUS's transparent longest-artifact simplification while preserving SERFF provenance."
        )
        if not release:
            release = CorpusRelease(
                name=name,
                version=version,
                description="LOCUS-style harmonized access layer for public SERFF filings.",
                selection_method=selection_method,
            )
            session.add(release)
            session.flush()
        release.selection_method = selection_method
        session.execute(delete(HarmonizedFiling).where(HarmonizedFiling.release_id == release.id))

        filing_rows = session.execute(select(Filing)).scalars().all()
        scopes: dict[tuple[str, str, str], list[tuple[Filing, int, int, int, int]]] = {}
        for filing in filing_rows:
            state = filing.state or "UNKNOWN"
            line_of_business = filing.line_of_business or "unknown"
            company_name = filing.company_name or "unknown"
            attachment_count = session.scalar(select(func.count(Attachment.id)).where(Attachment.filing_id == filing.id)) or 0
            page_count = session.scalar(select(func.coalesce(func.sum(Attachment.page_count), 0)).where(Attachment.filing_id == filing.id)) or 0
            fact_count = session.scalar(select(func.count(ExtractedFact.id)).where(ExtractedFact.filing_id == filing.id)) or 0
            segment_count = session.scalar(
                select(func.count(FilingSegment.id)).where(
                    FilingSegment.filing_id == filing.id,
                    FilingSegment.is_substantive.is_(True),
                )
            ) or 0
            scopes.setdefault((state, line_of_business, company_name), []).append(
                (filing, attachment_count, page_count, fact_count, segment_count)
            )

        harmonized_count = 0
        for (state, line_of_business, company_name), candidates in scopes.items():
            ranked = sorted(
                candidates,
                key=lambda item: (item[2] * 10 + item[3] + item[4], item[1], item[0].serff_tracking_number),
                reverse=True,
            )
            filing, attachment_count, page_count, fact_count, segment_count = ranked[0]
            score = float(page_count * 10 + fact_count + segment_count)
            session.add(
                HarmonizedFiling(
                    release_id=release.id,
                    filing_id=filing.id,
                    state=state,
                    line_of_business=line_of_business,
                    company_name=company_name,
                    selection_rank=1,
                    selection_score=score,
                    selection_reason="highest page-weighted processed-corpus score in scope",
                    page_count=page_count,
                    attachment_count=attachment_count,
                    fact_count=fact_count,
                    segment_count=segment_count,
                )
            )
            harmonized_count += 1
        session.commit()
        return dtos.ReleaseBuildResult(
            release_id=release.id,
            scopes_seen=len(scopes),
            harmonized_filings_created=harmonized_count,
        )


class FilingSearchService:
    @staticmethod
    def search(session: Session, query: str, limit: int = 10) -> list[dtos.SearchHit]:
        return search(session, query, limit)


class FilingExportService:
    @staticmethod
    def export_actuarial(session: Session, out_dir: Path) -> dtos.ExportResult:
        return export_actuarial_tables(session, out_dir)

    @staticmethod
    def export_review(
        session: Session,
        output_path: Path,
        limit: int | None = None,
        *,
        include_all: bool = False,
    ) -> dtos.ExportResult:
        return export_review_csv(session, output_path, limit, include_all=include_all)


class FilingSummaryService:
    @staticmethod
    def get_summary(session: Session) -> dtos.SummaryResult:
        return dtos.SummaryResult(
            filings=session.scalar(select(func.count(Filing.id))) or 0,
            attachments=session.scalar(select(func.count(Attachment.id))) or 0,
            segments=session.scalar(select(func.count(FilingSegment.id))) or 0,
            extracted_facts=session.scalar(select(func.count(ExtractedFact.id))) or 0,
        )

    @staticmethod
    def list_facts(session: Session, serff: str | None, limit: int) -> list[ExtractedFact]:
        query = select(ExtractedFact).order_by(ExtractedFact.id).limit(limit)
        if serff:
            filing = session.scalar(select(Filing).where(Filing.serff_tracking_number == serff))
            if not filing:
                return []
            query = select(ExtractedFact).where(ExtractedFact.filing_id == filing.id).order_by(ExtractedFact.id).limit(limit)
        return list(session.scalars(query))
