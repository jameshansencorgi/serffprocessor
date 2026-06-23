from __future__ import annotations

import argparse
from pathlib import Path

from serff_intel.config import load_settings
from serff_intel.models import Attachment, Filing
from serff_intel.services import (
    CorpusReleaseService,
    FilingExportService,
    FilingImportService,
    FilingProcessingService,
    FilingSearchService,
    FilingSummaryService,
)
from serff_intel.storage.db import init_db, make_engine, session_factory


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="serff-intel")
    parser.add_argument("--root", default=".", help="Project root containing data/ and pyproject.toml.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db")

    import_parser = sub.add_parser("import-folder")
    import_parser.add_argument("folder")
    import_parser.add_argument("--state")

    import_all_parser = sub.add_parser("import-tree")
    import_all_parser.add_argument("root_folder")

    manifest_parser = sub.add_parser("import-s3-manifest")
    manifest_parser.add_argument("manifest_csv")

    comp_parser = sub.add_parser("import-comp-search-run")
    comp_parser.add_argument("results_json")

    sub.add_parser("process-pending")
    sub.add_parser("build-index")

    release_parser = sub.add_parser("build-release")
    release_parser.add_argument("--name", default="SERFF-LOCUS")
    release_parser.add_argument("--version", default="v0.1")

    search_parser = sub.add_parser("search")
    search_parser.add_argument("query")
    search_parser.add_argument("--limit", type=int, default=10)

    facts_parser = sub.add_parser("facts")
    facts_parser.add_argument("--serff")
    facts_parser.add_argument("--limit", type=int, default=50)

    export_parser = sub.add_parser("export-actuarial")
    export_parser.add_argument("out_dir")

    review_parser = sub.add_parser("export-review")
    review_parser.add_argument("output_csv")
    review_parser.add_argument("--limit", type=int)

    sub.add_parser("summary")

    args = parser.parse_args(argv)
    settings = load_settings(args.root)
    engine = make_engine(settings)
    init_db(engine)
    Session = session_factory(engine)

    with Session() as session:
        if args.command == "init-db":
            print(f"Initialized database at {settings.db_url}")
        elif args.command == "import-folder":
            filing = FilingImportService.import_folder(session, Path(args.folder), state=args.state)
            print(f"Imported {filing.state} {filing.serff_tracking_number} as filing_id={filing.id}")
        elif args.command == "import-tree":
            result = FilingImportService.import_tree(session, Path(args.root_folder))
            print(f"Imported {result.filings_imported} filing folders from {result.folders_seen} discovered folders")
        elif args.command == "import-s3-manifest":
            result = FilingImportService.import_manifest(session, Path(args.manifest_csv))
            print(
                f"Imported {result.rows_seen} manifest rows, "
                f"{result.filing_bundles_created} new filing bundles, {result.attachments_created} new attachments"
            )
        elif args.command == "import-comp-search-run":
            result = FilingImportService.import_comp_search_run(session, Path(args.results_json))
            print(
                f"Imported {result.rows_seen} comp-search attachment rows, "
                f"{result.filing_bundles_created} new filing bundles, {result.attachments_created} new attachments"
            )
        elif args.command == "process-pending":
            result = FilingProcessingService.process_pending(session, settings)
            print(
                "Processed "
                f"{result.attachments_processed} attachments, {result.pages_created} pages, "
                f"{result.segments_created} segments, "
                f"{result.facts_created} facts, {result.chunks_created} chunks"
            )
        elif args.command == "build-index":
            count = FilingProcessingService.rebuild_search_index(session)
            print(f"Indexed {count} pages")
        elif args.command == "build-release":
            result = CorpusReleaseService.build_harmonized_release(session, name=args.name, version=args.version)
            print(
                f"Built release_id={result.release_id}: "
                f"{result.harmonized_filings_created} harmonized filings across {result.scopes_seen} scopes"
            )
        elif args.command == "search":
            hits = FilingSearchService.search(session, args.query, args.limit)
            for hit in hits:
                filing = session.get(Filing, hit.filing_id)
                attachment = session.get(Attachment, hit.attachment_id)
                label = f"{filing.state} {filing.serff_tracking_number}" if filing else f"filing_id={hit.filing_id}"
                filename = attachment.filename if attachment else f"attachment_id={hit.attachment_id}"
                print(f"- {label} | {filename} | page {hit.page_number}: {hit.snippet}")
            if not hits:
                print("No hits.")
        elif args.command == "facts":
            for fact in FilingSummaryService.list_facts(session, args.serff, args.limit):
                filing = session.get(Filing, fact.filing_id)
                print(
                    f"- {filing.serff_tracking_number if filing else fact.filing_id} "
                    f"{fact.fact_type}={fact.fact_value!r} "
                    f"conf={fact.confidence:.2f} page={fact.page_number} evidence={fact.evidence_text[:180]!r}"
                )
        elif args.command == "export-actuarial":
            result = FilingExportService.export_actuarial(session, Path(args.out_dir))
            print(f"Exported {result.rows_written} rows across {result.files_written} actuarial CSV files")
        elif args.command == "export-review":
            result = FilingExportService.export_review(session, Path(args.output_csv), limit=args.limit)
            print(f"Exported {result.rows_written} review rows to {args.output_csv}")
        elif args.command == "summary":
            result = FilingSummaryService.get_summary(session)
            print(f"Filings: {result.filings}")
            print(f"Attachments: {result.attachments}")
            print(f"Segments: {result.segments}")
            print(f"Extracted facts: {result.extracted_facts}")


if __name__ == "__main__":
    main()
