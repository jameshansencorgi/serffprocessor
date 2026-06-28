from __future__ import annotations

from dataclasses import dataclass
import re

from serff_intel.extract.context import normalize_key


@dataclass(frozen=True)
class TableCandidate:
    table_index: int
    table_name: str | None
    table_kind: str
    rows: list[list[str]]
    confidence: float
    needs_review: bool
    locator_text: str


NUMERIC_RE = re.compile(r"[-$]?\d[\d,.]*%?")
SPLIT_RE = re.compile(r"\s{2,}|\t+|\s+\|\s+")


def extract_table_candidates(text_value: str) -> list[TableCandidate]:
    candidates: list[TableCandidate] = []
    current: list[str] = []
    pending_header: str | None = None
    table_index = 1
    for line in text_value.splitlines():
        stripped = line.strip()
        if _is_table_like(stripped):
            if not current and pending_header:
                current.append(pending_header)
            current.append(stripped)
            pending_header = None
            continue
        if len(current) >= 2:
            candidates.append(_candidate_from_lines(table_index, current))
            table_index += 1
        pending_header = stripped if _could_be_header(stripped) else None
        current = []
    if len(current) >= 2:
        candidates.append(_candidate_from_lines(table_index, current))
    return candidates


def _candidate_from_lines(table_index: int, lines: list[str]) -> TableCandidate:
    rows = [_split_row(line) for line in lines]
    kind = _infer_table_kind("\n".join(lines))
    confidence = _table_confidence(rows, kind)
    return TableCandidate(
        table_index=table_index,
        table_name=_infer_table_name(lines),
        table_kind=kind,
        rows=rows,
        confidence=confidence,
        needs_review=confidence < 0.72,
        locator_text="\n".join(lines[:4]),
    )


def _is_table_like(line: str) -> bool:
    if not line:
        return False
    number_count = len(NUMERIC_RE.findall(line))
    has_separator = "|" in line or "\t" in line or bool(re.search(r"\s{2,}", line))
    return number_count >= 3 or (number_count >= 2 and has_separator)


def _could_be_header(line: str) -> bool:
    return bool(line and any(char.isalpha() for char in line) and re.search(r"\s{2,}|\t+|\|", line))


def _split_row(line: str) -> list[str]:
    parts = [part.strip() for part in SPLIT_RE.split(line) if part.strip()]
    if len(parts) <= 1:
        parts = line.split()
    return parts


def _table_confidence(rows: list[list[str]], kind: str) -> float:
    if len(rows) < 2:
        return 0.3
    row_widths = [len(row) for row in rows if row]
    if not row_widths:
        return 0.3
    target_width = max(set(row_widths), key=row_widths.count)
    rectangular_ratio = sum(1 for width in row_widths if width == target_width) / len(row_widths)
    numeric_cells = sum(1 for row in rows for cell in row if NUMERIC_RE.fullmatch(cell.replace(",", "")))
    total_cells = sum(len(row) for row in rows)
    numeric_ratio = numeric_cells / total_cells if total_cells else 0
    has_header = bool(rows[0] and any(any(char.isalpha() for char in cell) for cell in rows[0]))
    known_kind_bonus = 0.08 if kind != "unknown" else 0
    score = 0.35 + 0.30 * rectangular_ratio + 0.20 * min(1.0, numeric_ratio * 2) + known_kind_bonus
    if has_header:
        score += 0.10
    if target_width < 3:
        score -= 0.15
    return max(0.0, min(0.95, score))


def _infer_table_name(lines: list[str]) -> str | None:
    first = lines[0].strip()
    if len(first) < 120 and any(char.isalpha() for char in first):
        return first
    return None


def _infer_table_kind(text_value: str) -> str:
    lower = text_value.lower()
    if "loss cost multiplier" in lower or "permissible loss" in lower:
        return "lcm_support"
    if "profit" in lower or "return on equity" in lower:
        return "profit_support"
    if "expense" in lower or "commission" in lower or "taxes" in lower:
        return "expense_support"
    if "trend" in lower or "frequency" in lower or "severity" in lower:
        return "trend_support"
    if "territory" in lower or "relativity" in lower or "factor" in lower:
        return "rating_factor_grid"
    if "rate change" in lower or "impact" in lower:
        return "rate_impact"
    return "unknown"


def cell_address(row_index: int, col_index: int) -> str:
    return f"R{row_index}C{col_index}"


def cell_labels(rows: list[list[str]], row_index: int, col_index: int) -> tuple[str | None, str | None, str | None, str | None]:
    row_label = rows[row_index - 1][0] if rows[row_index - 1] else None
    col_label = rows[0][col_index - 1] if rows and len(rows[0]) >= col_index else None
    return row_label, normalize_key(row_label), col_label, normalize_key(col_label)
