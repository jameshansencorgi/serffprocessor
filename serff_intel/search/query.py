from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from serff_intel import dtos


def search(session: Session, query: str, limit: int = 10) -> list[dtos.SearchHit]:
    rows = session.execute(
        text(
            "SELECT filing_id, attachment_id, page_number, snippet(filing_fts, 3, '[', ']', ' ... ', 18) AS snippet "
            "FROM filing_fts WHERE filing_fts MATCH :query LIMIT :limit"
        ),
        {"query": _fts_query(query), "limit": limit},
    ).mappings()
    return [
        dtos.SearchHit(
            filing_id=int(row["filing_id"]),
            attachment_id=int(row["attachment_id"]),
            page_number=int(row["page_number"]),
            snippet=str(row["snippet"]),
        )
        for row in rows
    ]


def _fts_query(query: str) -> str:
    terms = [term.strip().replace('"', "") for term in query.split() if term.strip()]
    return " OR ".join(f'"{term}"' for term in terms) or '""'
