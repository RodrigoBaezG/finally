"""Typed query helpers for FinAlly.

All write functions commit their own transactions.
All functions use parameterized queries — no string-format SQL.
UUIDs are generated with uuid.uuid4().hex (32-char hex string, no hyphens).
Timestamps are ISO-8601 UTC strings.
"""

import json
import sqlite3
import uuid
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


# ---------------------------------------------------------------------------
# users_profile
# ---------------------------------------------------------------------------

def get_user_profile(conn: sqlite3.Connection, user_id: str = "default") -> dict:
    """Return the user profile row as a dict.

    Raises KeyError if the profile does not exist.
    """
    row = conn.execute(
        "SELECT * FROM users_profile WHERE id = ?", (user_id,)
    ).fetchone()
    if row is None:
        raise KeyError(f"User profile not found: {user_id!r}")
    return _row_to_dict(row)


def update_cash_balance(
    conn: sqlite3.Connection, user_id: str, new_balance: float
) -> None:
    """Set the cash_balance for the given user."""
    conn.execute(
        "UPDATE users_profile SET cash_balance = ? WHERE id = ?",
        (new_balance, user_id),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# watchlist
# ---------------------------------------------------------------------------

def list_watchlist(conn: sqlite3.Connection, user_id: str = "default") -> list[dict]:
    """Return all watchlist rows for the user, ordered by added_at ascending."""
    rows = conn.execute(
        "SELECT * FROM watchlist WHERE user_id = ? ORDER BY added_at ASC",
        (user_id,),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def add_watchlist_ticker(
    conn: sqlite3.Connection, ticker: str, user_id: str = "default"
) -> dict:
    """Insert a ticker into the watchlist.

    Raises sqlite3.IntegrityError if the (user_id, ticker) pair already exists.
    Returns the newly inserted row as a dict.
    """
    row_id = _new_id()
    now = _now()
    conn.execute(
        "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
        (row_id, user_id, ticker, now),
    )
    conn.commit()
    return {"id": row_id, "user_id": user_id, "ticker": ticker, "added_at": now}


def remove_watchlist_ticker(
    conn: sqlite3.Connection, ticker: str, user_id: str = "default"
) -> bool:
    """Delete a ticker from the watchlist.

    Returns True if a row was deleted, False if ticker was not in the list.
    """
    cursor = conn.execute(
        "DELETE FROM watchlist WHERE user_id = ? AND ticker = ?",
        (user_id, ticker),
    )
    conn.commit()
    return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# positions
# ---------------------------------------------------------------------------

def get_position(
    conn: sqlite3.Connection, ticker: str, user_id: str = "default"
) -> dict | None:
    """Return the position row for a ticker, or None if not held."""
    row = conn.execute(
        "SELECT * FROM positions WHERE user_id = ? AND ticker = ?",
        (user_id, ticker),
    ).fetchone()
    return _row_to_dict(row) if row else None


def list_positions(conn: sqlite3.Connection, user_id: str = "default") -> list[dict]:
    """Return all open positions for the user."""
    rows = conn.execute(
        "SELECT * FROM positions WHERE user_id = ? ORDER BY ticker ASC",
        (user_id,),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def upsert_position(
    conn: sqlite3.Connection,
    ticker: str,
    quantity: float,
    avg_cost: float,
    user_id: str = "default",
) -> None:
    """Insert or update a position.

    If quantity <= 0 the row is deleted (position fully closed).
    """
    if quantity <= 0:
        conn.execute(
            "DELETE FROM positions WHERE user_id = ? AND ticker = ?",
            (user_id, ticker),
        )
        conn.commit()
        return

    now = _now()
    existing = conn.execute(
        "SELECT id FROM positions WHERE user_id = ? AND ticker = ?",
        (user_id, ticker),
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE positions SET quantity = ?, avg_cost = ?, updated_at = ? "
            "WHERE user_id = ? AND ticker = ?",
            (quantity, avg_cost, now, user_id, ticker),
        )
    else:
        conn.execute(
            "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (_new_id(), user_id, ticker, quantity, avg_cost, now),
        )
    conn.commit()


# ---------------------------------------------------------------------------
# trades
# ---------------------------------------------------------------------------

def insert_trade(
    conn: sqlite3.Connection,
    ticker: str,
    side: str,
    quantity: float,
    price: float,
    user_id: str = "default",
) -> dict:
    """Append a trade to the trades log.

    Returns the inserted row as a dict.
    """
    row_id = _new_id()
    now = _now()
    conn.execute(
        "INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (row_id, user_id, ticker, side, quantity, price, now),
    )
    conn.commit()
    return {
        "id": row_id,
        "user_id": user_id,
        "ticker": ticker,
        "side": side,
        "quantity": quantity,
        "price": price,
        "executed_at": now,
    }


def list_trades(
    conn: sqlite3.Connection,
    user_id: str = "default",
    limit: int | None = None,
) -> list[dict]:
    """Return trades for the user, most-recent first.

    Pass limit to cap the number of rows returned.
    """
    if limit is not None:
        rows = conn.execute(
            "SELECT * FROM trades WHERE user_id = ? ORDER BY executed_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM trades WHERE user_id = ? ORDER BY executed_at DESC",
            (user_id,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# portfolio_snapshots
# ---------------------------------------------------------------------------

def insert_portfolio_snapshot(
    conn: sqlite3.Connection,
    total_value: float,
    user_id: str = "default",
) -> None:
    """Record a portfolio value snapshot."""
    conn.execute(
        "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) "
        "VALUES (?, ?, ?, ?)",
        (_new_id(), user_id, total_value, _now()),
    )
    conn.commit()


def list_portfolio_snapshots(
    conn: sqlite3.Connection,
    user_id: str = "default",
    limit: int | None = None,
) -> list[dict]:
    """Return portfolio snapshots, oldest first.

    Pass limit to cap the number of rows returned.
    """
    if limit is not None:
        rows = conn.execute(
            "SELECT * FROM portfolio_snapshots WHERE user_id = ? "
            "ORDER BY recorded_at ASC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM portfolio_snapshots WHERE user_id = ? ORDER BY recorded_at ASC",
            (user_id,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# chat_messages
# ---------------------------------------------------------------------------

def insert_chat_message(
    conn: sqlite3.Connection,
    role: str,
    content: str,
    actions: list | dict | None = None,
    user_id: str = "default",
) -> dict:
    """Insert a chat message.

    actions should be a Python list/dict (or None); it is serialized to JSON
    before storage. Returns the inserted row as a dict with actions already
    JSON-parsed.
    """
    row_id = _new_id()
    now = _now()
    actions_json = json.dumps(actions) if actions is not None else None
    conn.execute(
        "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (row_id, user_id, role, content, actions_json, now),
    )
    conn.commit()
    return {
        "id": row_id,
        "user_id": user_id,
        "role": role,
        "content": content,
        "actions": actions,
        "created_at": now,
    }


def list_chat_messages(
    conn: sqlite3.Connection,
    user_id: str = "default",
    limit: int = 20,
) -> list[dict]:
    """Return chat messages in chronological order (oldest first).

    actions TEXT column is JSON-parsed back to Python objects (or None).
    """
    rows = conn.execute(
        "SELECT * FROM chat_messages WHERE user_id = ? ORDER BY created_at ASC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    result = []
    for row in rows:
        d = _row_to_dict(row)
        d["actions"] = json.loads(d["actions"]) if d["actions"] is not None else None
        result.append(d)
    return result
