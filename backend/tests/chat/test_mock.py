"""Tests for the deterministic LLM mock."""

from __future__ import annotations

from app.chat.mock import generate_mock_response

EMPTY_CTX = {"cash_balance": 10000.0, "total_portfolio_value": 10000.0, "positions": []}


def test_buy_intent():
    result = generate_mock_response("buy 5 AAPL", EMPTY_CTX)
    assert result["trades"] == [{"ticker": "AAPL", "side": "buy", "quantity": 5.0}]
    assert result["watchlist_changes"] == []


def test_purchase_synonym():
    result = generate_mock_response("purchase 2 shares of MSFT", EMPTY_CTX)
    assert result["trades"] == [{"ticker": "MSFT", "side": "buy", "quantity": 2.0}]


def test_sell_intent():
    result = generate_mock_response("sell 10 TSLA", EMPTY_CTX)
    assert result["trades"] == [{"ticker": "TSLA", "side": "sell", "quantity": 10.0}]


def test_fractional_quantity():
    result = generate_mock_response("buy 1.5 NVDA", EMPTY_CTX)
    assert result["trades"][0]["quantity"] == 1.5


def test_default_quantity_is_one():
    result = generate_mock_response("buy AAPL", EMPTY_CTX)
    assert result["trades"] == [{"ticker": "AAPL", "side": "buy", "quantity": 1.0}]


def test_add_to_watchlist():
    result = generate_mock_response("add PYPL to my watchlist", EMPTY_CTX)
    assert result["watchlist_changes"] == [{"ticker": "PYPL", "action": "add"}]
    assert result["trades"] == []


def test_watch_verb():
    result = generate_mock_response("watch COIN", EMPTY_CTX)
    assert result["watchlist_changes"] == [{"ticker": "COIN", "action": "add"}]


def test_remove_from_watchlist():
    result = generate_mock_response("remove NFLX from my watchlist", EMPTY_CTX)
    assert result["watchlist_changes"] == [{"ticker": "NFLX", "action": "remove"}]


def test_portfolio_query_empty():
    result = generate_mock_response("analyze my portfolio", EMPTY_CTX)
    assert result["trades"] == []
    assert result["watchlist_changes"] == []
    assert "no open positions" in result["message"].lower()


def test_portfolio_query_with_positions():
    ctx = {
        "cash_balance": 5000.0,
        "total_portfolio_value": 7000.0,
        "positions": [
            {
                "ticker": "AAPL",
                "quantity": 10,
                "avg_cost": 180.0,
                "current_price": 200.0,
                "unrealized_pnl": 200.0,
                "pnl_pct": 11.11,
            }
        ],
    }
    result = generate_mock_response("how am I doing?", ctx)
    assert "AAPL" in result["message"]
    assert result["trades"] == []


def test_default_greeting():
    result = generate_mock_response("hello there", EMPTY_CTX)
    assert result["trades"] == []
    assert result["watchlist_changes"] == []
    assert "FinAlly" in result["message"]


def test_buy_doesnt_trigger_watchlist_add():
    # "buy AAPL" should NOT also add AAPL to watchlist
    result = generate_mock_response("buy 5 AAPL", EMPTY_CTX)
    assert len(result["trades"]) == 1
    assert result["watchlist_changes"] == []


def test_multiple_trades_in_message():
    result = generate_mock_response("buy 5 AAPL and sell 3 TSLA", EMPTY_CTX)
    tickers = {t["ticker"] for t in result["trades"]}
    assert tickers == {"AAPL", "TSLA"}


def test_deterministic_same_input_same_output():
    a = generate_mock_response("buy 5 AAPL", EMPTY_CTX)
    b = generate_mock_response("buy 5 AAPL", EMPTY_CTX)
    assert a == b
