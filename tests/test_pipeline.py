from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from serff_intel.config import load_settings
from serff_intel.ingest.manual_import import import_filing_folder
from serff_intel.models import ExtractedFact, Filing
from serff_intel.pipeline import process_pending
from serff_intel.search.query import search
from serff_intel.storage.db import init_db, make_engine, session_factory


def test_sample_pipeline(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    settings = load_settings(root)
    settings = settings.__class__(
        root_dir=root,
        db_url=f"sqlite:///{tmp_path / 'serff.sqlite'}",
        raw_dir=settings.raw_dir,
        processed_dir=tmp_path / "processed",
    )
    engine = make_engine(settings)
    init_db(engine)
    Session = session_factory(engine)

    with Session() as session:
        filing = import_filing_folder(session, root / "data/raw/filings/TX/ACME-133700001")
        assert filing.serff_tracking_number == "ACME-133700001"
        counts = process_pending(session, settings)
        assert counts.attachments_processed == 2
        assert counts.facts_created >= 8
        requested = session.scalar(
            select(ExtractedFact).where(ExtractedFact.fact_type == "requested_rate_change")
        )
        assert requested is not None
        assert requested.normalized_value == "12.4"
        hits = search(session, "nuclear verdicts trucking", limit=5)
        assert hits
        stored = session.scalar(select(Filing).where(Filing.serff_tracking_number == "ACME-133700001"))
        assert stored is not None
        assert stored.company_name == "Acme Mutual Insurance Company"
