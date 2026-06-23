from __future__ import annotations

import hashlib
import json
import csv
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from serff_intel import dtos
from serff_intel.models import Attachment, Filing, RawFilingBundle, RawS3Object

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".csv", ".docx", ".xlsx", ".xlsm"}


def import_filing_folder(session: Session, folder: Path, default_state: str | None = None) -> Filing:
    folder = folder.resolve()
    metadata = _load_metadata(folder / "metadata.json")
    state = (metadata.get("state") or default_state or folder.parent.name).upper()
    serff_tracking_number = metadata.get("serff_tracking_number") or folder.name

    bundle = session.scalar(
        select(RawFilingBundle).where(
            RawFilingBundle.state == state,
            RawFilingBundle.serff_tracking_number == serff_tracking_number,
        )
    )
    if not bundle:
        bundle = RawFilingBundle(
            state=state,
            serff_tracking_number=serff_tracking_number,
            source=metadata.get("source", "manual"),
            s3_prefix=metadata.get("s3_prefix"),
            coverage_status="imported",
            raw_metadata_json=json.dumps(metadata, sort_keys=True),
        )
        session.add(bundle)
        session.flush()

    filing = session.scalar(
        select(Filing).where(Filing.state == state, Filing.serff_tracking_number == serff_tracking_number)
    )
    if not filing:
        filing = Filing(
            raw_bundle_id=bundle.id,
            serff_tracking_number=serff_tracking_number,
            state=state,
        )
        session.add(filing)
    _apply_metadata(filing, metadata)
    session.flush()

    for file_path in sorted(folder.iterdir()):
        if not file_path.is_file() or file_path.name == "metadata.json":
            continue
        if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        sha = sha256_file(file_path)
        raw = session.scalar(select(RawS3Object).where(RawS3Object.sha256 == sha))
        if not raw:
            raw = RawS3Object(
                bucket=metadata.get("bucket"),
                key=metadata.get("s3_key_prefix", "") + file_path.name if metadata.get("s3_key_prefix") else None,
                etag=None,
                sha256=sha,
                size_bytes=file_path.stat().st_size,
                content_type=_content_type(file_path),
                last_modified=datetime.fromtimestamp(file_path.stat().st_mtime, UTC).replace(tzinfo=None),
                local_cache_path=str(file_path),
                raw_metadata_json=json.dumps({"source_folder": str(folder)}, sort_keys=True),
            )
            session.add(raw)
            session.flush()
        attachment = session.scalar(
            select(Attachment).where(Attachment.filing_id == filing.id, Attachment.sha256 == sha)
        )
        if not attachment:
            session.add(
                Attachment(
                    filing_id=filing.id,
                    raw_s3_object_id=raw.id,
                    filename=file_path.name,
                    file_type=file_path.suffix.lower().lstrip("."),
                    local_path=str(file_path),
                    sha256=sha,
                    parse_status="pending",
                    raw_metadata_json=json.dumps({"source_folder": str(folder)}, sort_keys=True),
                )
            )
    session.commit()
    return filing


def discover_filing_folders(root: Path) -> list[Path]:
    root = root.resolve()
    folders: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_dir() and any(child.is_file() and child.suffix.lower() in SUPPORTED_EXTENSIONS for child in path.iterdir()):
            folders.append(path)
    return folders


def import_s3_manifest(session: Session, manifest_path: Path) -> dtos.ManifestImportResult:
    rows_seen = 0
    filing_bundles_created = 0
    attachments_created = 0
    with manifest_path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows_seen += 1
            local_path = Path(row["local_path"]).expanduser().resolve()
            if not local_path.exists():
                raise FileNotFoundError(f"manifest local_path does not exist: {local_path}")
            state = row["state"].upper()
            serff = row["serff_tracking_number"]
            bundle = session.scalar(
                select(RawFilingBundle).where(
                    RawFilingBundle.state == state,
                    RawFilingBundle.serff_tracking_number == serff,
                )
            )
            if not bundle:
                bundle = RawFilingBundle(
                    state=state,
                    serff_tracking_number=serff,
                    source="s3-manifest",
                    s3_prefix=_prefix_from_key(row.get("key", "")),
                    coverage_status="imported",
                    raw_metadata_json=json.dumps(row, sort_keys=True),
                )
                session.add(bundle)
                session.flush()
                filing_bundles_created += 1
            filing = session.scalar(select(Filing).where(Filing.state == state, Filing.serff_tracking_number == serff))
            if not filing:
                filing = Filing(
                    raw_bundle_id=bundle.id,
                    serff_tracking_number=serff,
                    state=state,
                    company_name=row.get("company_name") or None,
                    line_of_business=row.get("line_of_business") or None,
                    raw_metadata_json=json.dumps(row, sort_keys=True),
                )
                session.add(filing)
                session.flush()
            sha = sha256_file(local_path)
            raw = session.scalar(select(RawS3Object).where(RawS3Object.sha256 == sha))
            if not raw:
                raw = RawS3Object(
                    bucket=row.get("bucket") or None,
                    key=row.get("key") or None,
                    etag=row.get("etag") or None,
                    sha256=sha,
                    size_bytes=local_path.stat().st_size,
                    content_type=row.get("content_type") or _content_type(local_path),
                    last_modified=datetime.fromtimestamp(local_path.stat().st_mtime, UTC).replace(tzinfo=None),
                    local_cache_path=str(local_path),
                    raw_metadata_json=json.dumps(row, sort_keys=True),
                )
                session.add(raw)
                session.flush()
            attachment = session.scalar(
                select(Attachment).where(Attachment.filing_id == filing.id, Attachment.sha256 == sha)
            )
            if not attachment:
                session.add(
                    Attachment(
                        filing_id=filing.id,
                        raw_s3_object_id=raw.id,
                        filename=local_path.name,
                        file_type=(row.get("file_type") or local_path.suffix.lower().lstrip(".")),
                        local_path=str(local_path),
                        sha256=sha,
                        parse_status="pending",
                        raw_metadata_json=json.dumps(row, sort_keys=True),
                    )
                )
                attachments_created += 1
    session.commit()
    return dtos.ManifestImportResult(
        rows_seen=rows_seen,
        filing_bundles_created=filing_bundles_created,
        attachments_created=attachments_created,
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_metadata(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _apply_metadata(filing: Filing, metadata: dict[str, Any]) -> None:
    for key in (
        "insurance_type",
        "sub_type",
        "line_of_business",
        "company_name",
        "naic_company_code",
        "group_name",
        "filing_type",
        "status",
        "source_url",
    ):
        if metadata.get(key) is not None:
            setattr(filing, key, metadata[key])
    for key in ("submitted_date", "disposition_date", "effective_date"):
        if metadata.get(key):
            setattr(filing, key, datetime.fromisoformat(metadata[key]).date())
    for key in ("rate_impact_requested", "rate_impact_approved"):
        if metadata.get(key) is not None:
            setattr(filing, key, float(metadata[key]))
    filing.raw_metadata_json = json.dumps(metadata, sort_keys=True)


def _content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".pdf": "application/pdf",
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".csv": "text/csv",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
    }.get(suffix, "application/octet-stream")


def _prefix_from_key(key: str) -> str | None:
    if not key or "/" not in key:
        return None
    return key.rsplit("/", 1)[0] + "/"
