from __future__ import annotations

import re


SERFF_RE = re.compile(r"\b([A-Z]{3,5}[- ]?1?\d{6,10})\b")
NAIC_RE = re.compile(r"\bNAIC(?:\s+Company)?(?:\s+Code)?[:\s#-]+(\d{4,6})\b", re.I)
COMPANY_RE = re.compile(r"(?:Company Name|Insurer|Carrier)[:\s]+(.{3,120})", re.I)


def extract_metadata_from_text(text: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    if match := SERFF_RE.search(text):
        metadata["serff_tracking_number"] = match.group(1).replace(" ", "-")
    if match := NAIC_RE.search(text):
        metadata["naic_company_code"] = match.group(1)
    if match := COMPANY_RE.search(text):
        metadata["company_name"] = _clean_line(match.group(1))
    return metadata


def _clean_line(value: str) -> str:
    return value.splitlines()[0].strip(" .:-")

