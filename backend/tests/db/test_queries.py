"""Tests for backend/app/db/queries.py.

Each test uses a fresh isolated temp DB via the `conn` fixture.
"""

import json
import sqlite3

import pytest

from app.db import queries
from app.db.connection import get_connection

# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def conn(tmp_path, monkeypatch):
    """Fresh database connection for each test."""
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("FINALLY_DB_PATH", str(db_file))
    c = get_connection(db_file)
    yield c
    c.close()


# ---------------------------------------------------------------------------
# users_profile
# ---------------------------------------------------------------------------

class TestGetUserProfile:
    def test_returns_default_profile(self, conn):
        profile = queries.get_user_profile(conn)
        assert profile["id"] == "default"
        assert profile["cash_balance"] == 10000.0

    def test_raises_key_error_for_unknown_user(self, conn):
        with pytest.raises(KeyError, match="nonexistent"):
            queries.get_user_profile(conn, user_id="nonexistent")


class TestUpdateCashBalance:
    def test_updates_balance(self, conn):
        queries.update_cash_balance(conn, "default", 5000.0)
        profile = queries.get_user_profile(conn)
        assert profile["cash_balance"] == 5000.0

    def test_balance_can_be_zero(self, conn):
        queries.update_cash_balance(conn, "default", 0.0)
        assert queries.get_user_profile(conn)["cash_balance"] == 0.0

    def test_balance_persists_across_reads(self, conn):
        queries.update_cash_balance(conn, "default", 7777.77)
        assert queries.get_user_profile(conn)["cash_balance"] == pytest.approx(7777.77)


# ---------------------------------------------------------------------------
# watchlist
# ---------------------------------------------------------------------------

class TestListWatchlist:
    def test_returns_seeded_entries(self, conn):
        entries = queries.list_watchlist(conn)
        assert len(entries) == 10
        tickers = {e["ticker"] for e in entries}
        assert "AAPL" in tickers

    def test_empty_for_unknown_user(self, conn):
        assert queries.list_watchlist(conn, user_id="ghost") == []


class TestAddWatchlistTicker:
    def test_adds_new_ticker(self, conn):
        queries.add_watchlist_ticker(conn, "UBER")
        tickers = {e["ticker"] for e in queries.list_watchlist(conn)}
        assert "UBER" in tickers

    def test_returns_inserted_row(self, conn):
        result = queries.add_watchlist_ticker(conn, "UBER")
        assert result["ticker"] == "UBER"
        assert result["user_id"] == "default"
        assert "id" in result
        assert "added_at" in result

    def test_duplicate_raises_integrity_error(self, conn):
        with pytest.raises(sqlite3.IntegrityError):
            queries.add_watchlist_ticker(conn, "AAPL")  # already seeded

    def test_same_ticker_different_user_allowed(self, conn):
        # Insert default user profile for "other" to avoid FK issues (no FK here, just testing)
        result = queries.add_watchlist_ticker(conn, "AAPL", user_id="other")
        assert result["ticker"] == "AAPL"
        assert result["user_id"] == "other"


class TestRemoveWatchlistTicker:
    def test_removes_existing_ticker(self, conn):
        removed = queries.remove_watchlist_ticker(conn, "AAPL")
        assert removed is True
        tickers = {e["ticker"] for e in queries.list_watchlist(conn)}
        assert "AAPL" not in tickers

    def test_returns_false_for_missing_ticker(self, conn):
        assert queries.remove_watchlist_ticker(conn, "FAKEXYZ") is False

    def test_count_decrements(self, conn):
        before = len(queries.list_watchlist(conn))
        queries.remove_watchlist_ticker(conn, "AAPL")
        after = len(queries.list_watchlist(conn))
        assert after == before - 1


# ---------------------------------------------------------------------------
# positions
# ---------------------------------------------------------------------------

class TestGetPosition:
    def test_returns_none_when_no_position(self, conn):
        assert queries.get_position(conn, "AAPL") is None

    def test_returns_position_after_upsert(self, conn):
        queries.upsert_position(conn, "AAPL", 10.0, 150.0)
        pos = queries.get_position(conn, "AAPL")
        assert pos is not None
        assert pos["ticker"] == "AAPL"
        assert pos["quantity"] == 10.0
        assert pos["avg_cost"] == 150.0


class TestListPositions:
    def test_empty_initially(self, conn):
        assert queries.list_positions(conn) == []

    def test_lists_all_positions(self, conn):
        queries.upsert_position(conn, "AAPL", 5.0, 180.0)
        queries.upsert_position(conn, "GOOGL", 2.0, 170.0)
        positions = queries.list_positions(conn)
        tickers = {p["ticker"] for p in positions}
        assert tickers == {"AAPL", "GOOGL"}


class TestUpsertPosition:
    def test_inserts_new_position(self, conn):
        queries.upsert_position(conn, "MSFT", 3.0, 400.0)
        pos = queries.get_position(conn, "MSFT")
        assert pos["quantity"] == 3.0
        assert pos["avg_cost"] == 400.0

    def test_updates_existing_position(self, conn):
        queries.upsert_position(conn, "MSFT", 3.0, 400.0)
        queries.upsert_position(conn, "MSFT", 6.0, 380.0)
        pos = queries.get_position(conn, "MSFT")
        assert pos["quantity"] == 6.0
        assert pos["avg_cost"] == 380.0

    def test_deletes_row_when_quantity_zero(self, conn):
        queries.upsert_position(conn, "MSFT", 3.0, 400.0)
        queries.upsert_position(conn, "MSFT", 0.0, 400.0)
        assert queries.get_position(conn, "MSFT") is None

    def test_deletes_row_when_quantity_negative(self, conn):
        queries.upsert_position(conn, "TSLA", 2.0, 250.0)
        queries.upsert_position(conn, "TSLA", -1.0, 250.0)
        assert queries.get_position(conn, "TSLA") is None

    def test_unique_per_user_and_ticker(self, conn):
        queries.upsert_position(conn, "AAPL", 10.0, 150.0)
        queries.upsert_position(conn, "AAPL", 20.0, 160.0, user_id="other")
        pos_default = queries.get_position(conn, "AAPL", user_id="default")
        pos_other = queries.get_position(conn, "AAPL", user_id="other")
        assert pos_default["quantity"] == 10.0
        assert pos_other["quantity"] == 20.0


# ---------------------------------------------------------------------------
# trades
# ---------------------------------------------------------------------------

class TestInsertTrade:
    def test_inserts_and_returns_row(self, conn):
        trade = queries.insert_trade(conn, "AAPL", "buy", 10.0, 150.0)
        assert trade["ticker"] == "AAPL"
        assert trade["side"] == "buy"
        assert trade["quantity"] == 10.0
        assert trade["price"] == 150.0
        assert "id" in trade
        assert "executed_at" in trade

    def test_invalid_side_raises(self, conn):
        with pytest.raises(sqlite3.IntegrityError):
            queries.insert_trade(conn, "AAPL", "hold", 1.0, 100.0)

    def test_multiple_trades_accumulate(self, conn):
        queries.insert_trade(conn, "AAPL", "buy", 5.0, 150.0)
        queries.insert_trade(conn, "AAPL", "sell", 2.0, 155.0)
        trades = queries.list_trades(conn)
        assert len(trades) == 2


class TestListTrades:
    def test_empty_initially(self, conn):
        assert queries.list_trades(conn) == []

    def test_most_recent_first(self, conn):
        queries.insert_trade(conn, "AAPL", "buy", 1.0, 150.0)
        queries.insert_trade(conn, "GOOGL", "buy", 2.0, 170.0)
        trades = queries.list_trades(conn)
        # Most recent first — GOOGL was inserted last
        assert trades[0]["ticker"] == "GOOGL"
        assert trades[1]["ticker"] == "AAPL"

    def test_limit_parameter(self, conn):
        for i in range(5):
            queries.insert_trade(conn, "AAPL", "buy", float(i + 1), 150.0)
        trades = queries.list_trades(conn, limit=3)
        assert len(trades) == 3

    def test_limit_none_returns_all(self, conn):
        for i in range(5):
            queries.insert_trade(conn, "AAPL", "buy", float(i + 1), 150.0)
        trades = queries.list_trades(conn, limit=None)
        assert len(trades) == 5


# ---------------------------------------------------------------------------
# portfolio_snapshots
# ---------------------------------------------------------------------------

class TestInsertPortfolioSnapshot:
    def test_inserts_snapshot(self, conn):
        queries.insert_portfolio_snapshot(conn, 12345.67)
        snapshots = queries.list_portfolio_snapshots(conn)
        assert len(snapshots) == 1
        assert snapshots[0]["total_value"] == pytest.approx(12345.67)

    def test_multiple_snapshots_stored(self, conn):
        queries.insert_portfolio_snapshot(conn, 10000.0)
        queries.insert_portfolio_snapshot(conn, 10500.0)
        queries.insert_portfolio_snapshot(conn, 9800.0)
        assert len(queries.list_portfolio_snapshots(conn)) == 3


class TestListPortfolioSnapshots:
    def test_empty_initially(self, conn):
        assert queries.list_portfolio_snapshots(conn) == []

    def test_oldest_first(self, conn):
        queries.insert_portfolio_snapshot(conn, 10000.0)
        queries.insert_portfolio_snapshot(conn, 11000.0)
        snapshots = queries.list_portfolio_snapshots(conn)
        assert snapshots[0]["total_value"] == pytest.approx(10000.0)
        assert snapshots[1]["total_value"] == pytest.approx(11000.0)

    def test_limit_parameter(self, conn):
        for v in [1.0, 2.0, 3.0, 4.0, 5.0]:
            queries.insert_portfolio_snapshot(conn, v)
        assert len(queries.list_portfolio_snapshots(conn, limit=3)) == 3

    def test_limit_none_returns_all(self, conn):
        for v in [1.0, 2.0, 3.0]:
            queries.insert_portfolio_snapshot(conn, v)
        assert len(queries.list_portfolio_snapshots(conn, limit=None)) == 3


# ---------------------------------------------------------------------------
# chat_messages
# ---------------------------------------------------------------------------

class TestInsertChatMessage:
    def test_inserts_user_message(self, conn):
        msg = queries.insert_chat_message(conn, "user", "Hello", actions=None)
        assert msg["role"] == "user"
        assert msg["content"] == "Hello"
        assert msg["actions"] is None

    def test_inserts_assistant_message_with_actions(self, conn):
        actions = [{"type": "trade", "ticker": "AAPL", "side": "buy", "quantity": 5}]
        msg = queries.insert_chat_message(conn, "assistant", "Bought AAPL", actions=actions)
        assert msg["actions"] == actions

    def test_returned_dict_has_all_fields(self, conn):
        msg = queries.insert_chat_message(conn, "user", "test")
        for field in ("id", "user_id", "role", "content", "actions", "created_at"):
            assert field in msg


class TestListChatMessages:
    def test_empty_initially(self, conn):
        assert queries.list_chat_messages(conn) == []

    def test_chronological_order(self, conn):
        queries.insert_chat_message(conn, "user", "first")
        queries.insert_chat_message(conn, "assistant", "second")
        msgs = queries.list_chat_messages(conn)
        assert msgs[0]["content"] == "first"
        assert msgs[1]["content"] == "second"

    def test_default_limit_20(self, conn):
        for i in range(25):
            queries.insert_chat_message(conn, "user", f"msg {i}")
        msgs = queries.list_chat_messages(conn)
        assert len(msgs) == 20

    def test_custom_limit(self, conn):
        for i in range(10):
            queries.insert_chat_message(conn, "user", f"msg {i}")
        assert len(queries.list_chat_messages(conn, limit=5)) == 5

    def test_actions_json_round_trip(self, conn):
        """actions stored as JSON TEXT are parsed back to Python objects."""
        actions = {"trades": [{"ticker": "TSLA", "side": "sell", "quantity": 1}]}
        queries.insert_chat_message(conn, "assistant", "Sold TSLA", actions=actions)
        msgs = queries.list_chat_messages(conn)
        assert msgs[-1]["actions"] == actions

    def test_none_actions_stays_none(self, conn):
        queries.insert_chat_message(conn, "user", "no actions")
        msgs = queries.list_chat_messages(conn)
        assert msgs[-1]["actions"] is None

    def test_actions_stored_as_json_text_in_db(self, conn):
        """Verify the raw DB column is a JSON string, not a Python object."""
        actions = [{"ticker": "NVDA", "side": "buy", "quantity": 2}]
        queries.insert_chat_message(conn, "assistant", "Bought NVDA", actions=actions)
        raw = conn.execute(
            "SELECT actions FROM chat_messages ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        # The column should be a string that parses to our original list
        assert isinstance(raw["actions"], str)
        assert json.loads(raw["actions"]) == actions

    def test_invalid_role_raises(self, conn):
        with pytest.raises(sqlite3.IntegrityError):
            queries.insert_chat_message(conn, "system", "bad role")
