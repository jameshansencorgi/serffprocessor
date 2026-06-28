from __future__ import annotations

import re


def infer_coverage(filename: str, text_value: str = "") -> str | None:
    haystack = f"{filename}\n{text_value[:1200]}".upper()
    matches: list[str] = []
    for token in ("AL", "APD", "BI", "PD", "UM", "UIM", "PIP", "COMP", "COLL"):
        if re.search(rf"(?<![A-Z0-9]){re.escape(token)}(?![A-Z0-9])", haystack):
            matches.append(token)
    if not matches:
        return None
    return "/".join(dict.fromkeys(matches))


def normalize_key(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return normalized or None
