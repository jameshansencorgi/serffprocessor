from __future__ import annotations

from pathlib import Path
import json

from sqlalchemy import func, select
import yaml

from serff_intel.classify.document_classifier import classify_document
from serff_intel.config import load_settings
from serff_intel.export import export_actuarial_tables, export_review_csv
from serff_intel.extract.rate_impact import extract_rate_facts
from serff_intel.extract.tables import extract_table_candidates
from serff_intel.ingest.comp_search import import_comp_search_run
from serff_intel.ingest.manual_import import import_filing_folder
from serff_intel.models import (
    Attachment,
    AttachmentParseDecision,
    DocumentPage,
    ExtractedFact,
    ExtractedTable,
    Filing,
    HarmonizedFiling,
    ProcessingError,
)
from serff_intel.pipeline import process_pending
from serff_intel.parsing.router import decide_parse_route
from serff_intel.parsing.text_extract import PageText
from serff_intel.search.query import search
from serff_intel.services import CorpusReleaseService
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
        assert counts.segments_created >= 2
        assert counts.facts_created >= 8
        release = CorpusReleaseService.build_harmonized_release(session)
        assert release.harmonized_filings_created == 1
        harmonized = session.scalar(select(HarmonizedFiling))
        assert harmonized is not None
        assert harmonized.segment_count >= 2
        requested = session.scalar(
            select(ExtractedFact).where(ExtractedFact.fact_type == "requested_rate_change")
        )
        assert requested is not None
        assert requested.normalized_value == "12.4"
        assert requested.role == "requested"
        assert requested.snapshot_filing_id == filing.id
        hits = search(session, "nuclear verdicts trucking", limit=5)
        assert hits
        stored = session.scalar(select(Filing).where(Filing.serff_tracking_number == "ACME-133700001"))
        assert stored is not None
        assert stored.company_name == "Acme Mutual Insurance Company"


def test_comp_search_import_and_exports(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    settings = load_settings(root)
    settings = settings.__class__(
        root_dir=root,
        db_url=f"sqlite:///{tmp_path / 'serff.sqlite'}",
        raw_dir=settings.raw_dir,
        processed_dir=tmp_path / "processed",
    )
    attachment_path = tmp_path / "Actuarial Memo.txt"
    attachment_path.write_text(
        "SERFF Tracking Number: TEST-134000001\n"
        "Company Name: Test Carrier\n"
        "Actuarial Memorandum\n"
        "The requested rate change is 7.5%.\n"
        "Loss Cost Multiplier Q / P 1.234\n"
        "Underwriting Profit Provision 8.0%.\n"
        "Coverage  Premium  Loss  Ratio\n"
        "AL        100000   65000 65%\n"
        "APD       80000    52000 65%\n"
    )
    results_path = tmp_path / "results.json"
    results_path.write_text(json.dumps(_comp_search_payload(attachment_path)))
    engine = make_engine(settings)
    init_db(engine)
    Session = session_factory(engine)

    with Session() as session:
        imported = import_comp_search_run(session, results_path)
        assert imported.rows_seen == 1
        assert imported.filing_bundles_created == 1
        assert imported.attachments_created == 1
        assert session.scalar(select(Attachment)) is not None
        processed = process_pending(session, settings)
        assert processed.facts_created >= 3
        high_value_facts = session.scalars(
            select(ExtractedFact).where(
                ExtractedFact.fact_type.in_(
                    {
                        "requested_rate_change",
                        "approved_rate_change",
                        "indicated_rate_level_change",
                        "selected_rate_level_change",
                        "loss_cost_multiplier",
                        "profit_provision",
                    }
                )
            )
        ).all()
        assert high_value_facts
        assert all(fact.fact_key and fact.fact_key != "unknown" for fact in high_value_facts)
        assert session.scalar(select(ExtractedTable)) is not None
        decision = session.scalar(select(AttachmentParseDecision))
        assert decision is not None
        assert decision.extraction_route == "plain_text_or_unknown"
        assert decision.value_tier == "high_value_actuarial"
        CorpusReleaseService.build_harmonized_release(session)
        actuarial_export = export_actuarial_tables(session, tmp_path / "exports")
        review_export = export_review_csv(session, tmp_path / "review" / "facts.csv")
        assert actuarial_export.files_written == 11
        assert actuarial_export.rows_written > 0
        assert review_export.rows_written > 0
        assert (tmp_path / "exports" / "rate_changes.csv").read_text().count("requested_rate_change") == 1
        assert "requested_overall_rate_change" in (tmp_path / "exports" / "rate_changes.csv").read_text()
        assert "corrected_value" in (tmp_path / "review" / "facts.csv").read_text()
        assert "review_reason" in (tmp_path / "review" / "facts.csv").read_text()
        assert "extraction_route" in (tmp_path / "exports" / "attachments.csv").read_text()
        assert "role" in (tmp_path / "exports" / "loss_cost_multipliers.csv").read_text()
        assert (tmp_path / "exports" / "extracted_tables.csv").exists()
        assert (tmp_path / "exports" / "extracted_table_cells.csv").exists()


def test_process_pending_limit_dry_run_and_serff_filter(tmp_path: Path) -> None:
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
        import_filing_folder(session, root / "data/raw/filings/TX/ACME-133700001")

        dry_run = process_pending(session, settings, limit=1, dry_run=True)
        assert dry_run.attachments_processed == 1
        assert session.scalar(select(func.count(DocumentPage.id))) == 0
        assert session.scalar(select(func.count(ExtractedFact.id))) == 0

        processed = process_pending(session, settings, limit=1)
        assert processed.attachments_processed == 1
        assert session.scalar(select(func.count(Attachment.id)).where(Attachment.parse_status == "parsed")) == 1

        skipped = process_pending(session, settings, serff="NOPE-000000000")
        assert skipped.attachments_processed == 0
        assert session.scalar(select(func.count(Attachment.id)).where(Attachment.parse_status == "parsed")) == 1


def test_process_pending_records_processing_error_and_continues(tmp_path: Path, monkeypatch) -> None:
    import serff_intel.pipeline as pipeline_module

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
    original_parse_document = pipeline_module.parse_document
    calls = 0

    def flaky_parse_document(path: Path):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("parser boom")
        return original_parse_document(path)

    monkeypatch.setattr(pipeline_module, "parse_document", flaky_parse_document)

    with Session() as session:
        import_filing_folder(session, root / "data/raw/filings/TX/ACME-133700001")
        result = pipeline_module.process_pending(session, settings)
        assert result.attachments_processed == 2
        error = session.scalar(select(ProcessingError))
        assert error is not None
        assert error.stage == "parse"
        assert error.exception_type == "RuntimeError"
        assert "parser boom" in error.message
        assert session.scalar(select(func.count(Attachment.id)).where(Attachment.parse_status == "parsed")) == 1


def test_process_pending_preserves_committed_stages_when_chunking_fails(tmp_path: Path, monkeypatch) -> None:
    import serff_intel.pipeline as pipeline_module

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

    def failing_classify_segment(text: str):
        raise RuntimeError("chunk boom")

    monkeypatch.setattr(pipeline_module, "classify_segment", failing_classify_segment)

    with Session() as session:
        import_filing_folder(session, root / "data/raw/filings/TX/ACME-133700001")
        result = pipeline_module.process_pending(session, settings)
        assert result.attachments_processed == 2
        assert result.pages_created > 0
        assert result.facts_created > 0
        assert result.segments_created == 0
        assert session.scalar(select(func.count(DocumentPage.id))) == result.pages_created
        assert session.scalar(select(func.count(ExtractedFact.id))) == result.facts_created
        assert session.scalar(select(func.count(ProcessingError.id)).where(ProcessingError.stage == "chunk")) == 2


def test_process_pending_retry_failed_is_explicit_and_terminal(tmp_path: Path, monkeypatch) -> None:
    import serff_intel.pipeline as pipeline_module

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

    def failing_parse_document(path: Path):
        raise RuntimeError("permanent parse boom")

    monkeypatch.setattr(pipeline_module, "parse_document", failing_parse_document)

    with Session() as session:
        import_filing_folder(session, root / "data/raw/filings/TX/ACME-133700001")

        first = pipeline_module.process_pending(session, settings, max_retries=2)
        assert first.attachments_processed == 2
        assert session.scalar(select(func.count(Attachment.id)).where(Attachment.parse_status == "failed")) == 2
        assert session.scalar(select(func.count(Attachment.id)).where(Attachment.retry_count == 1)) == 2

        default_skip = pipeline_module.process_pending(session, settings, max_retries=2)
        assert default_skip.attachments_processed == 0

        retry = pipeline_module.process_pending(session, settings, retry_failed=True, max_retries=2)
        assert retry.attachments_processed == 2
        assert session.scalar(select(func.count(Attachment.id)).where(Attachment.terminal_failed.is_(True))) == 2

        terminal_skip = pipeline_module.process_pending(session, settings, retry_failed=True, max_retries=2)
        assert terminal_skip.attachments_processed == 0


def test_serff_specific_document_classification() -> None:
    examples = [
        (
            "TX Exhibit G (AL/APD).pdf",
            "Loss Cost Multiplier calculation with variable expense and expected loss ratio.",
            "lcm_exhibit",
        ),
        (
            "Frequency and Severity Trend Selections as of 2025-06.pdf",
            "Frequency trend and severity trend selections are shown below.",
            "trend_exhibit",
        ),
        (
            "Accredited Authorization Letter - TX.pdf",
            "The company is authorized to file this rate/rule filing.",
            "authorization_letter",
        ),
        (
            "Brazos LDF Selections as of 2025-06.pdf",
            "Selected loss development factor by age.",
            "ldf_exhibit",
        ),
    ]
    for filename, text, expected in examples:
        assert classify_document(filename, text).document_class == expected


def test_parse_decision_tree_flags_tables_ocr_and_store_only() -> None:
    table_decision = decide_parse_route(
        file_type="pdf",
        pages=[
            PageText(
                1,
                "\n".join(
                    [
                        "Loss Cost Multiplier support",
                        "Coverage Premium Loss Ratio",
                        "AL 100,000 65,000 65%",
                        "APD 80,000 52,000 65%",
                        "Total 180,000 117,000 65%",
                    ]
                ),
            )
        ],
        document_class="lcm_exhibit",
        failures=[],
    )
    assert table_decision.extraction_route == "native_text_table_aware"
    assert table_decision.value_tier == "high_value_actuarial"

    ocr_decision = decide_parse_route(
        file_type="pdf",
        pages=[PageText(1, "")],
        document_class="rate_indication",
        failures=["pdfplumber extracted no text"],
    )
    assert ocr_decision.extraction_route == "parse_failed"
    assert ocr_decision.ocr_needed is True

    store_decision = decide_parse_route(
        file_type="pdf",
        pages=[PageText(1, "Approval letter. The department has approved the filing." * 10)],
        document_class="approval_letter",
        failures=[],
    )
    assert store_decision.extraction_route == "native_text_store_only"
    assert store_decision.value_tier == "store_only"


def test_fact_catalogue_enforces_role_table_and_snapshot_fields() -> None:
    root = Path(__file__).resolve().parents[1]
    catalogue = yaml.safe_load((root / "docs/fact_catalogue.yml").read_text())
    fields = set(catalogue["default_provenance_fields"])
    for field in (
        "role",
        "table_id",
        "row_label",
        "col_label",
        "cell_address",
        "snapshot_filing_id",
        "effective_start_date",
        "supersedes_fact_id",
        "supersession_status",
    ):
        assert field in fields
    allowed_roles = set(catalogue["role_enum"])
    for group in catalogue["fact_groups"].values():
        for fact in group["facts"].values():
            for role in fact.get("roles", []):
                assert role in allowed_roles


def test_rate_extractor_normalizes_roles_and_review_flags() -> None:
    facts = extract_rate_facts(
        "Indicated Loss Cost Multiplier = 2.002\n"
        "Indicated Loss Cost Multiplier Offset for Risk Load 1.901\n"
        "Selected Loss Cost Multiplier 1.901\n"
        "Loss Cost Multiplier Q / P 1.234\n"
        "Selected underwriting profit provision 9.0%\n",
        page_number=1,
    )
    lcms = [fact for fact in facts if fact.fact_type == "loss_cost_multiplier"]
    assert any(fact.normalized_value == "2.002" and fact.role == "indicated" for fact in lcms)
    assert any(fact.normalized_value == "1.901" and fact.role == "offset" for fact in lcms)
    assert any(fact.normalized_value == "1.901" and fact.role == "selected" for fact in lcms)
    ambiguous = [fact for fact in lcms if fact.normalized_value == "1.234"]
    assert ambiguous
    assert ambiguous[0].role == "unknown"
    assert ambiguous[0].needs_review is True
    assert any(fact.fact_type == "profit_provision" and fact.role == "selected" for fact in facts)


def test_table_extraction_keeps_row_column_structure() -> None:
    tables = extract_table_candidates(
        "Loss Cost Multiplier Support\n"
        "Coverage  Premium  Loss  Ratio\n"
        "AL        100000   65000 65%\n"
        "APD       80000    52000 65%\n"
    )
    assert len(tables) == 1
    assert tables[0].needs_review is False
    assert tables[0].confidence >= 0.72
    assert tables[0].rows[1][0] == "AL"
    assert tables[0].rows[1][1] == "100000"


def test_low_confidence_table_extraction_stays_review_flagged() -> None:
    tables = extract_table_candidates(
        "Some  Header\n"
        "AL    100000\n"
        "APD   missing words 52000 65%\n"
    )
    assert len(tables) == 1
    assert tables[0].needs_review is True


def _comp_search_payload(attachment_path: Path) -> dict:
    return {
        "run_id": "test-run",
        "filings": [
            {
                "tracking_number": "TEST-134000001",
                "filing_id": "134000001",
                "state": "TX",
                "carrier": "Test Carrier",
                "naic_code": "99999",
                "business_type": "P&C",
                "toi": "20.0 Commercial Auto",
                "sub_toi": "20.0000 Commercial Auto Combinations",
                "filing_type": "Rate/Rule",
                "filing_status": "Approved",
                "submission_date": "01/15/2026",
                "disposition_date": "02/01/2026",
                "attachments": [
                    {
                        "section": "Supporting Documentation",
                        "form_name": "Actuarial Memorandum",
                        "filename": attachment_path.name,
                        "local_path": str(attachment_path),
                    }
                ],
            }
        ],
    }
