from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from serff_intel import dtos
from serff_intel.ingest.manual_import import sha256_file
from serff_intel.models import Attachment, Filing, RawFilingBundle, RawS3Object


def import_comp_search_run(session: Session, results_path: Path) -> dtos.CompSearchImportResult:
    payload = json.loads(results_path.read_text())
    rows_seen = 0
    filing_bundles_created = 0
    attachments_created = 0
    seen_paths: set[str] = set()
    run_id = payload.get("run_id", results_path.parent.name)

    for filing_payload in payload.get("filings", []):
        bundle, bundle_created = _get_or_create_bundle(session, filing_payload, run_id)
        filing_bundles_created += 1 if bundle_created else 0
        filing = _get_or_create_filing(session, bundle, filing_payload)
        session.flush()
        for attachment_payload in filing_payload.get("attachments", []):
            local_path_value = attachment_payload.get("local_path")
            if not local_path_value:
                continue
            local_path = Path(local_path_value).expanduser().resolve()
            if str(local_path) in seen_paths:
                continue
            seen_paths.add(str(local_path))
            rows_seen += 1
            if not local_path.exists():
                raise FileNotFoundError(f"comp-search local_path does not exist: {local_path}")
            attachment_created = _import_attachment(
                session=session,
                filing=filing,
                local_path=local_path,
                run_id=run_id,
                filing_payload=filing_payload,
                attachment_payload=attachment_payload,
            )
            attachments_created += 1 if attachment_created else 0

    session.commit()
    return dtos.CompSearchImportResult(
        rows_seen=rows_seen,
        filing_bundles_created=filing_bundles_created,
        attachments_created=attachments_created,
    )


def _get_or_create_bundle(session: Session, filing_payload: dict[str, Any], run_id: str) -> tuple[RawFilingBundle, bool]:
    state = str(filing_payload["state"]).upper()
    tracking_number = str(filing_payload["tracking_number"])
    bundle = session.scalar(
        select(RawFilingBundle).where(
            RawFilingBundle.state == state,
            RawFilingBundle.serff_tracking_number == tracking_number,
        )
    )
    if bundle:
        return bundle, False
    bundle = RawFilingBundle(
        state=state,
        serff_tracking_number=tracking_number,
        source="serff-comp-search",
        s3_prefix=f"serff-comp-search/{run_id}/{tracking_number}/",
        coverage_status="imported",
        raw_metadata_json=json.dumps(filing_payload, sort_keys=True),
    )
    session.add(bundle)
    session.flush()
    return bundle, True


def _get_or_create_filing(session: Session, bundle: RawFilingBundle, filing_payload: dict[str, Any]) -> Filing:
    state = str(filing_payload["state"]).upper()
    tracking_number = str(filing_payload["tracking_number"])
    filing = session.scalar(select(Filing).where(Filing.state == state, Filing.serff_tracking_number == tracking_number))
    if not filing:
        filing = Filing(
            raw_bundle_id=bundle.id,
            serff_tracking_number=tracking_number,
            state=state,
        )
        session.add(filing)
    filing.company_name = filing_payload.get("carrier")
    filing.naic_company_code = filing_payload.get("naic_code")
    filing.line_of_business = filing_payload.get("toi")
    filing.sub_type = filing_payload.get("sub_toi")
    filing.insurance_type = filing_payload.get("business_type")
    filing.filing_type = filing_payload.get("filing_type")
    filing.status = filing_payload.get("filing_status")
    filing.submitted_date = _parse_date(filing_payload.get("submission_date"))
    filing.disposition_date = _parse_date(filing_payload.get("disposition_date"))
    filing.raw_metadata_json = json.dumps(filing_payload, sort_keys=True)
    return filing


def _import_attachment(
    session: Session,
    filing: Filing,
    local_path: Path,
    run_id: str,
    filing_payload: dict[str, Any],
    attachment_payload: dict[str, Any],
) -> bool:
    sha = sha256_file(local_path)
    raw = session.scalar(select(RawS3Object).where(RawS3Object.sha256 == sha))
    if not raw:
        raw = RawS3Object(
            bucket="serff-comp-search-local",
            key=f"serff-comp-search/{run_id}/{filing_payload['tracking_number']}/{local_path.name}",
            etag=None,
            sha256=sha,
            size_bytes=local_path.stat().st_size,
            content_type="application/pdf" if local_path.suffix.lower() == ".pdf" else "application/octet-stream",
            last_modified=datetime.fromtimestamp(local_path.stat().st_mtime).replace(tzinfo=None),
            local_cache_path=str(local_path),
            raw_metadata_json=json.dumps(attachment_payload, sort_keys=True),
        )
        session.add(raw)
        session.flush()
    attachment = session.scalar(select(Attachment).where(Attachment.filing_id == filing.id, Attachment.sha256 == sha))
    if attachment:
        return False
    session.add(
        Attachment(
            filing_id=filing.id,
            raw_s3_object_id=raw.id,
            filename=local_path.name,
            file_type=local_path.suffix.lower().lstrip("."),
            local_path=str(local_path),
            sha256=sha,
            parse_status="pending",
            raw_metadata_json=json.dumps(attachment_payload, sort_keys=True),
        )
    )
    return True


def _parse_date(value: str | None):
    if not value:
        return None
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None
