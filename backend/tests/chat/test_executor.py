"""Tests for execute_trade and execute_watchlist_change."""

from __future__ import annotations

from app.chat.execution import execute_trade, execute_watchlist_change
from app.db import queries


def test_buy_happy_path(test_conn, test_cache):
    result = execute_trade(test_conn, test_cache, "AAPL", "buy", 5.0)
    assert result.status == "executed"
    assert result.error is None
    assert result.price == 190.00

    profile = queries.get_user_profile(test_conn)
    assert profile["cash_balance"] == 10000.0 - 5 * 190.00

    pos = queries.get_position(test_conn, "AAPL")
    assert pos is not None
    assert pos["quantity"] == 5.0
    assert pos["avg_cost"] == 190.00


def test_buy_insufficient_cash(test_conn, test_cache):
    result = execute_trade(test_conn, test_cache, "NVDA", "buy", 100.0)
    assert result.status == "failed"
    assert "Insufficient cash" in result.error


def test_buy_unknown_ticker(test_conn, test_cache):
    # Not in cache and not in SEED_PRICES
    result = execute_trade(test_conn, test_cache, "XYZFOO", "buy", 1.0)
    assert result.status == "failed"
    assert "No market price" in result.error


def test_sell_happy_path(test_conn, test_cache):
    execute_trade(test_conn, test_cache, "AAPL", "buy", 10.0)
    result = execute_trade(test_conn, test_cache, "AAPL", "sell", 5.0)
    assert result.status == "executed"

    pos = queries.get_position(test_conn, "AAPL")
    assert pos is not None
    assert pos["quantity"] == 5.0


def test_sell_insufficient_shares(test_conn, test_cache):
    execute_trade(test_conn, test_cache, "AAPL", "buy", 2.0)
    result = execute_trade(test_conn, test_cache, "AAPL", "sell", 10.0)
    assert result.status == "failed"
    assert "Insufficient shares" in result.error


def test_sell_without_position(test_conn, test_cache):
    result = execute_trade(test_conn, test_cache, "AAPL", "sell", 1.0)
    assert result.status == "failed"
    assert "No position" in result.error


def test_sell_all_deletes_position(test_conn, test_cache):
    execute_trade(test_conn, test_cache, "AAPL", "buy", 5.0)
    execute_trade(test_conn, test_cache, "AAPL", "sell", 5.0)
    pos = queries.get_position(test_conn, "AAPL")
    assert pos is None


def test_invalid_side(test_conn, test_cache):
    result = execute_trade(test_conn, test_cache, "AAPL", "hold", 1.0)
    assert result.status == "failed"
    assert "Invalid side" in result.error


def test_invalid_quantity(test_conn, test_cache):
    result = execute_trade(test_conn, test_cache, "AAPL", "buy", 0.0)
    assert result.status == "failed"
    assert "positive" in result.error.lower()


def test_weighted_average_cost(test_conn, test_cache):
    execute_trade(test_conn, test_cache, "AAPL", "buy", 5.0)  # @ 190
    test_cache.update("AAPL", 200.0)
    execute_trade(test_conn, test_cache, "AAPL", "buy", 5.0)  # @ 200
    pos = queries.get_position(test_conn, "AAPL")
    assert pos["quantity"] == 10.0
    # Weighted average: (5*190 + 5*200) / 10 = 195
    assert pos["avg_cost"] == 195.0


def test_watchlist_add_valid_ticker(test_conn):
    # Clear seeded watchlist first
    queries.remove_watchlist_ticker(test_conn, "AAPL")
    result = execute_watchlist_change(test_conn, "AAPL", "add")
    assert result.status == "executed"
    tickers = {r["ticker"] for r in queries.list_watchlist(test_conn)}
    assert "AAPL" in tickers


def test_watchlist_add_unknown_ticker(test_conn):
    result = execute_watchlist_change(test_conn, "XYZFOO", "add")
    assert result.status == "failed"
    assert "Unknown ticker" in result.error


def test_watchlist_add_duplicate(test_conn):
    # AAPL is already in the seed data
    result = execute_watchlist_change(test_conn, "AAPL", "add")
    assert result.status == "failed"
    assert "already" in result.error.lower()


def test_watchlist_remove(test_conn):
    result = execute_watchlist_change(test_conn, "AAPL", "remove")
    assert result.status == "executed"
    tickers = {r["ticker"] for r in queries.list_watchlist(test_conn)}
    assert "AAPL" not in tickers


def test_watchlist_remove_missing(test_conn):
    queries.remove_watchlist_ticker(test_conn, "AAPL")
    result = execute_watchlist_change(test_conn, "AAPL", "remove")
    assert result.status == "failed"
    assert "not in the watchlist" in result.error


def test_watchlist_invalid_action(test_conn):
    result = execute_watchlist_change(test_conn, "AAPL", "swap")
    assert result.status == "failed"
    assert "Invalid action" in result.error
