"""Tests for backend/app/db/connection.py.

Each test gets a fresh temporary database file via the `db_conn` fixture.
No shared state between tests.
"""

import sqlite3

import pytest

from app.db.connection import get_connection, init_db

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Set FINALLY_DB_PATH to a temp file and return its Path."""
    db_file = tmp_path / "test_finally.db"
    monkeypatch.setenv("FINALLY_DB_PATH", str(db_file))
    return db_file


@pytest.fixture
def db_conn(tmp_db):
    """Return a connection to a fresh temp DB; close after test."""
    conn = get_connection(tmp_db)
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Schema creation
# ---------------------------------------------------------------------------

def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return {r[0] for r in rows}


def test_all_tables_created(db_conn):
    tables = _table_names(db_conn)
    expected = {
        "users_profile",
        "watchlist",
        "positions",
        "trades",
        "portfolio_snapshots",
        "chat_messages",
    }
    assert expected.issubset(tables)


def test_schema_idempotent(tmp_db):
    """Calling get_connection twice on the same DB must not error or duplicate tables."""
    conn1 = get_connection(tmp_db)
    conn1.close()
    conn2 = get_connection(tmp_db)
    tables = _table_names(conn2)
    conn2.close()
    assert "users_profile" in tables


def test_wal_mode_enabled(db_conn):
    mode = db_conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode == "wal"


def test_foreign_keys_enabled(db_conn):
    fk = db_conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert fk == 1


def test_row_factory_is_row(db_conn):
    row = db_conn.execute("SELECT * FROM users_profile WHERE id = 'default'").fetchone()
    assert row is not None
    assert isinstance(row, sqlite3.Row)


# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

def test_default_user_profile_seeded(db_conn):
    row = db_conn.execute(
        "SELECT * FROM users_profile WHERE id = 'default'"
    ).fetchone()
    assert row is not None
    assert row["cash_balance"] == 10000.0
    assert row["user_id"] == "default"


def test_default_watchlist_seeded(db_conn):
    rows = db_conn.execute(
        "SELECT ticker FROM watchlist WHERE user_id = 'default' ORDER BY ticker"
    ).fetchall()
    tickers = {r["ticker"] for r in rows}
    expected = {"AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"}
    assert tickers == expected


def test_seed_exactly_ten_watchlist_entries(db_conn):
    count = db_conn.execute(
        "SELECT COUNT(*) FROM watchlist WHERE user_id = 'default'"
    ).fetchone()[0]
    assert count == 10


def test_seed_idempotent_no_duplicate_profile(tmp_db):
    """Running init_db twice must not create a second profile row."""
    conn = get_connection(tmp_db)
    init_db(conn)  # second call
    count = conn.execute(
        "SELECT COUNT(*) FROM users_profile WHERE id = 'default'"
    ).fetchone()[0]
    conn.close()
    assert count == 1


def test_seed_idempotent_no_duplicate_watchlist(tmp_db):
    """Running init_db twice must not duplicate watchlist entries."""
    conn = get_connection(tmp_db)
    init_db(conn)
    count = conn.execute(
        "SELECT COUNT(*) FROM watchlist WHERE user_id = 'default'"
    ).fetchone()[0]
    conn.close()
    assert count == 10


# ---------------------------------------------------------------------------
# FINALLY_DB_PATH override
# ---------------------------------------------------------------------------

def test_env_var_overrides_db_path(tmp_path, monkeypatch):
    custom_path = tmp_path / "custom" / "my.db"
    monkeypatch.setenv("FINALLY_DB_PATH", str(custom_path))
    conn = get_connection()
    conn.close()
    assert custom_path.exists()
