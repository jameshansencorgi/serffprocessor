from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    root_dir: Path
    db_url: str
    raw_dir: Path
    processed_dir: Path

    @property
    def text_dir(self) -> Path:
        return self.processed_dir / "text"


def load_settings(root_dir: str | Path | None = None) -> Settings:
    root = Path(root_dir or os.getenv("SERFF_INTEL_ROOT", ".")).resolve()
    db_url = os.getenv("SERFF_INTEL_DB_URL", "sqlite:///data/db/serff_intel.sqlite")
    raw_dir = Path(os.getenv("SERFF_INTEL_RAW_DIR", "data/raw/filings"))
    processed_dir = Path(os.getenv("SERFF_INTEL_PROCESSED_DIR", "data/processed"))
    if not raw_dir.is_absolute():
        raw_dir = root / raw_dir
    if not processed_dir.is_absolute():
        processed_dir = root / processed_dir
    return Settings(root, db_url, raw_dir, processed_dir)


def resolve_sqlite_path(db_url: str, root_dir: Path) -> Path | None:
    prefix = "sqlite:///"
    if not db_url.startswith(prefix):
        return None
    raw = db_url[len(prefix) :]
    path = Path(raw)
    if not path.is_absolute():
        path = root_dir / path
    return path

