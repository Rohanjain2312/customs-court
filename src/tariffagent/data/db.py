"""SQLite storage for the HTS tree, notes, rulings, status and crosswalk."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from tariffagent.config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS revisions (
  name TEXT PRIMARY KEY, label TEXT, year INT, date TEXT, source TEXT, is_current INT DEFAULT 0
);
CREATE TABLE IF NOT EXISTS hts_rows (
  rev TEXT, idx INT, code TEXT, digits TEXT, indent INT, description TEXT, path TEXT,
  parent_idx INT, chapter TEXT, heading TEXT, section TEXT,
  general TEXT, special TEXT, other TEXT, units TEXT, footnotes TEXT, is_leaf INT,
  PRIMARY KEY (rev, idx)
);
CREATE INDEX IF NOT EXISTS hts_rows_code ON hts_rows(rev, digits);
CREATE INDEX IF NOT EXISTS hts_rows_parent ON hts_rows(rev, parent_idx);
CREATE TABLE IF NOT EXISTS notes (
  rev TEXT, scope TEXT, id TEXT, title TEXT, text TEXT, PRIMARY KEY (rev, scope, id)
);
CREATE TABLE IF NOT EXISTS rulings (
  id TEXT PRIMARY KEY, collection TEXT, date TEXT, subject TEXT, text TEXT,
  tariffs TEXT, related TEXT, modified_by TEXT, modifies TEXT, revoked_by TEXT, revokes TEXT,
  operationally_revoked INT, categories TEXT, source TEXT, has_meta INT DEFAULT 0
);
CREATE INDEX IF NOT EXISTS rulings_date ON rulings(date);
CREATE TABLE IF NOT EXISTS ruling_status (
  id TEXT PRIMARY KEY, status TEXT, linked TEXT, method TEXT, evidence TEXT
);
CREATE TABLE IF NOT EXISTS crosswalk (
  code TEXT PRIMARY KEY, current_code TEXT, method TEXT, stale INT
);
CREATE TABLE IF NOT EXISTS eval_redactions (
  ruling_id TEXT, dataset TEXT, item_id TEXT, confidence REAL, method TEXT,
  PRIMARY KEY (ruling_id, dataset, item_id)
);
"""


def connect(path: Path | None = None, readonly: bool = False) -> sqlite3.Connection:
    p = path or get_settings().db_path
    p.parent.mkdir(parents=True, exist_ok=True)
    if readonly:
        con = sqlite3.connect(f"file:{p}?mode=ro", uri=True, check_same_thread=False, timeout=120)
    else:
        con = sqlite3.connect(p, check_same_thread=False, timeout=120)
        con.execute("PRAGMA journal_mode=WAL")
        con.executescript(SCHEMA)
    con.row_factory = sqlite3.Row
    return con
