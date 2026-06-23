from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from serff_intel import dtos
from serff_intel.config import Settings
from serff_intel.ingest.manual_import import discover_filing_folders, import_filing_folder, import_s3_manifest
from serff_intel.models import Attachment, ExtractedFact, Filing
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


class FilingProcessingService:
    @staticmethod
    def process_pending(session: Session, settings: Settings) -> dtos.ProcessingResult:
        return process_pending(session, settings)

    @staticmethod
    def rebuild_search_index(session: Session) -> int:
        return rebuild_fts(session)


class FilingSearchService:
    @staticmethod
    def search(session: Session, query: str, limit: int = 10) -> list[dtos.SearchHit]:
        return search(session, query, limit)


class FilingSummaryService:
    @staticmethod
    def get_summary(session: Session) -> dtos.SummaryResult:
        return dtos.SummaryResult(
            filings=session.scalar(select(func.count(Filing.id))) or 0,
            attachments=session.scalar(select(func.count(Attachment.id))) or 0,
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
