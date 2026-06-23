from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ImportTreeResult:
    folders_seen: int
    filings_imported: int


@dataclass(frozen=True)
class ManifestImportResult:
    rows_seen: int
    filing_bundles_created: int
    attachments_created: int


@dataclass(frozen=True)
class ProcessingResult:
    attachments_processed: int
    pages_created: int
    segments_created: int
    facts_created: int
    chunks_created: int


@dataclass(frozen=True)
class ReleaseBuildResult:
    release_id: int
    scopes_seen: int
    harmonized_filings_created: int


@dataclass(frozen=True)
class SummaryResult:
    filings: int
    attachments: int
    segments: int
    extracted_facts: int


@dataclass(frozen=True)
class SearchHit:
    filing_id: int
    attachment_id: int
    page_number: int
    snippet: str
