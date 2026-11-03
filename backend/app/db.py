"""
Storage layer.

Dev: SQLite (zero-ops, ships with Python).
Prod: PostgreSQL + pgvector - swap `connect()` for SQLAlchemy/asyncpg and the
      `embedding` BLOB column becomes `vector(1536)`. Nothing else changes;
      see README "Production mapping".
"""
from __future__ import annotations

import json
import sqlite3
import struct
from contextlib import contextmanager
from typing import Any, Iterable

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT NOT NULL,
    url               TEXT,
    feed_url          TEXT UNIQUE NOT NULL,
    category          TEXT,
    authority         REAL DEFAULT 0.7,
    is_active         INTEGER DEFAULT 1,
    managed           INTEGER DEFAULT 0,
    last_fetched_at   TEXT,
    last_status       TEXT,
    last_error        TEXT,
    items_last_fetch  INTEGER DEFAULT 0,
    created_at        TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS articles (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id         INTEGER REFERENCES sources(id) ON DELETE SET NULL,
    title             TEXT NOT NULL,
    url               TEXT UNIQUE NOT NULL,
    author            TEXT,
    summary           TEXT,
    clean_text        TEXT,
    categories        TEXT DEFAULT '[]',
    tags              TEXT DEFAULT '[]',
    difficulty        TEXT DEFAULT 'intermediate',
    trending_score    REAL DEFAULT 0,
    priority_score    REAL DEFAULT 0,
    novelty           REAL DEFAULT 1,
    max_similarity    REAL DEFAULT 0,
    status            TEXT DEFAULT 'new',
    word_count        INTEGER DEFAULT 0,
    embedding         BLOB,
    lede_embedding    BLOB,
    dup_score         REAL DEFAULT 0,
    published_at      TEXT,
    scraped_at        TEXT DEFAULT (datetime('now')),
    created_at        TEXT DEFAULT (datetime('now')),
    duplicate_of      INTEGER,
    cluster_id        INTEGER,
    cluster_size      INTEGER DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_articles_status     ON articles(status);
CREATE INDEX IF NOT EXISTS idx_articles_priority   ON articles(priority_score DESC);
CREATE INDEX IF NOT EXISTS idx_articles_published  ON articles(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_duplicate  ON articles(duplicate_of);

CREATE TABLE IF NOT EXISTS drafts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id          INTEGER REFERENCES articles(id) ON DELETE CASCADE,
    draft_type          TEXT NOT NULL,
    generated_content   TEXT,
    human_edited_content TEXT,
    status              TEXT DEFAULT 'draft',
    provider            TEXT,
    created_at          TEXT DEFAULT (datetime('now')),
    updated_at          TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_drafts_article ON drafts(article_id);

-- document frequency table backing the incremental IDF used by the embedder
CREATE TABLE IF NOT EXISTS term_df (
    term TEXT PRIMARY KEY,
    df   INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- runtime settings overridden from the dashboard (see config.EDITABLE_SETTINGS)
CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
);
"""


# ---------------------------------------------------------------------------
# connection handling
# ---------------------------------------------------------------------------
def connect() -> sqlite3.Connection:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(settings.db_path), timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def db():
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with db() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)


def _migrate(conn: sqlite3.Connection) -> None:
    """
    Add columns introduced after a database was first created.

    `CREATE TABLE IF NOT EXISTS` never alters an existing table, so new columns
    need an explicit ADD COLUMN. SQLite has no IF NOT EXISTS for that, hence the
    PRAGMA check.
    """
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(sources)")}
    if "managed" not in existing:
        conn.execute("ALTER TABLE sources ADD COLUMN managed INTEGER DEFAULT 0")

    cols = {r["name"] for r in conn.execute("PRAGMA table_info(articles)")}
    for col, ddl in (("lede_embedding", "BLOB"), ("dup_score", "REAL DEFAULT 0"),
                     ("cluster_size", "INTEGER DEFAULT 1")):
        if col not in cols:
            conn.execute(f"ALTER TABLE articles ADD COLUMN {col} {ddl}")

    # Feeds that ship a zeroed struct_time (year 1) used to be stored as
    # 0001-01-01, which sinks those articles to the bottom of any
    # "newest first" ordering forever. Null them so COALESCE falls back to
    # scraped_at. ingest._struct_to_iso no longer produces these.
    conn.execute(
        "UPDATE articles SET published_at=NULL "
        "WHERE published_at IS NOT NULL AND published_at < '1970-01-01'"
    )


# ---------------------------------------------------------------------------
# vector (de)serialisation
# ---------------------------------------------------------------------------
def pack(vec: Iterable[float]) -> bytes:
    v = list(vec)
    return struct.pack(f"<{len(v)}f", *v)


def unpack(blob: bytes) -> tuple[float, ...]:
    n = len(blob) // 4
    return struct.unpack(f"<{n}f", blob)


# ---------------------------------------------------------------------------
# meta helpers
# ---------------------------------------------------------------------------
def get_meta(conn: sqlite3.Connection, key: str, default=None):
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    if row is None:
        return default
    try:
        return json.loads(row["value"])
    except Exception:
        return row["value"]


def set_meta(conn: sqlite3.Connection, key: str, value: Any) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, json.dumps(value)),
    )


#: binary columns are never serialised to JSON - drop them at the boundary
_BINARY_COLUMNS = {"embedding", "lede_embedding"}


def get_setting(conn: sqlite3.Connection, key: str, default=None):
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings(key, value, updated_at) VALUES(?, ?, datetime('now')) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
        "updated_at=datetime('now')",
        (key, value),
    )


def all_settings(conn: sqlite3.Connection) -> dict[str, str]:
    return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings")}


#: binary columns are never serialised to JSON - drop them at the boundary
_BINARY_COLUMNS = {"embedding", "lede_embedding"}


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    for col in _BINARY_COLUMNS:
        d.pop(col, None)
    for key in ("categories", "tags"):
        if isinstance(d.get(key), str):
            try:
                d[key] = json.loads(d[key])
            except Exception:
                d[key] = []
    return d
