from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from serff_intel.config import Settings, resolve_sqlite_path
from serff_intel.models import Base


def make_engine(settings: Settings) -> Engine:
    sqlite_path = resolve_sqlite_path(settings.db_url, settings.root_dir)
    if sqlite_path:
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        return create_engine(f"sqlite:///{sqlite_path}", future=True)
    return create_engine(settings.db_url, future=True)


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        if engine.dialect.name == "sqlite":
            existing_attachment_columns = {
                row[1] for row in conn.execute(text("PRAGMA table_info(attachment)")).all()
            }
            attachment_additions = {
                "retry_count": "INTEGER DEFAULT 0 NOT NULL",
                "last_error_stage": "VARCHAR(128)",
                "last_error_at": "DATETIME",
                "terminal_failed": "BOOLEAN DEFAULT 0 NOT NULL",
            }
            for column, ddl in attachment_additions.items():
                if column not in existing_attachment_columns:
                    conn.execute(text(f"ALTER TABLE attachment ADD COLUMN {column} {ddl}"))
        conn.execute(
            text(
                "CREATE VIRTUAL TABLE IF NOT EXISTS filing_fts USING fts5("
                "filing_id UNINDEXED, attachment_id UNINDEXED, page_number UNINDEXED, text)"
            )
        )


def reset_fts(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM filing_fts"))
