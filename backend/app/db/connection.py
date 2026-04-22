"""SQLite connection management for FinAlly.

Provides:
- get_connection(): returns a configured sqlite3.Connection
- get_db(): FastAPI dependency that yields a connection and closes it after
- init_db(): lazy initialization — creates schema and seeds data if needed

DB path defaults to db/finally.db (relative to the project root, which maps to
/app/db/finally.db inside the container). Override via FINALLY_DB_PATH env var.
"""

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def _resolve_db_path() -> Path:
    """Return the SQLite file path, honouring FINALLY_DB_PATH if set."""
    env_path = os.environ.get("FINALLY_DB_PATH")
    if env_path:
        return Path(env_path)
    # Default: project-root/db/finally.db
    # __file__ is backend/app/db/connection.py → go up 3 levels to project root
    project_root = Path(__file__).resolve().parents[3]
    return project_root / "db" / "finally.db"


_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "db" / "schema.sql"

# Default watchlist tickers for seed data
_DEFAULT_TICKERS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"]

# ---------------------------------------------------------------------------
# Connection factory
# ---------------------------------------------------------------------------

def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Return a configured sqlite3.Connection.

    Sets row_factory = sqlite3.Row and enables foreign keys.
    Triggers lazy initialization (schema + seed) on the first call for a
    given database file.
    """
    if db_path is None:
        db_path = _resolve_db_path()

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    _lazy_init(conn)
    return conn


# ---------------------------------------------------------------------------
# Lazy initialization
# ---------------------------------------------------------------------------

def _tables_exist(conn: sqlite3.Connection) -> bool:
    """Return True if the schema has already been applied."""
    row = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='users_profile'"
    ).fetchone()
    return row[0] > 0


def _seed_needed(conn: sqlite3.Connection) -> bool:
    """Return True if the default user profile is absent."""
    row = conn.execute(
        "SELECT COUNT(*) FROM users_profile WHERE id = 'default'"
    ).fetchone()
    return row[0] == 0


def _apply_schema(conn: sqlite3.Connection) -> None:
    """Execute schema.sql against the connection."""
    schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema_sql)


def _apply_seed(conn: sqlite3.Connection) -> None:
    """Insert default user profile and 10 default watchlist tickers."""
    now = datetime.now(timezone.utc).isoformat()

    conn.execute(
        "INSERT OR IGNORE INTO users_profile (id, user_id, cash_balance, created_at) "
        "VALUES ('default', 'default', 10000.0, ?)",
        (now,),
    )

    for ticker in _DEFAULT_TICKERS:
        conn.execute(
            "INSERT OR IGNORE INTO watchlist (id, user_id, ticker, added_at) "
            "VALUES (?, 'default', ?, ?)",
            (uuid.uuid4().hex, ticker, now),
        )

    conn.commit()


def init_db(conn: sqlite3.Connection) -> None:
    """Public entry point: ensure schema exists and seed data is present.

    Safe to call multiple times — idempotent.
    """
    _lazy_init(conn)


def _lazy_init(conn: sqlite3.Connection) -> None:
    """Internal: apply schema and seed only when necessary."""
    if not _tables_exist(conn):
        _apply_schema(conn)
    if _seed_needed(conn):
        _apply_seed(conn)


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

def get_db() -> Generator[sqlite3.Connection, None, None]:
    """FastAPI dependency: yield a connection and close it after the request."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()
