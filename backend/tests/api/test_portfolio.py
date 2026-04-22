"""Tests for portfolio endpoints.

Covers:
- GET /api/portfolio: seeded state, correct structure
- POST /api/portfolio/trade: buy, sell, weighted avg cost, sell-all, errors
- GET /api/portfolio/history: snapshot list
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import TEST_PRICES

# ---------------------------------------------------------------------------
# GET /api/portfolio
# ---------------------------------------------------------------------------


def test_portfolio_initial_state(client: TestClient) -> None:
    """Fresh DB should show $10k cash, no positions, total_value = 10000."""
    resp = client.get("/api/portfolio")
    assert resp.status_code == 200
    data = resp.json()
    assert data["cash_balance"] == pytest.approx(10_000.0, abs=0.01)
    assert data["total_value"] == pytest.approx(10_000.0, abs=0.01)
    assert data["total_unrealized_pnl"] == pytest.approx(0.0, abs=0.01)
    assert data["positions"] == []


def test_portfolio_response_shape(client: TestClient) -> None:
    """Response must include all required top-level keys."""
    data = client.get("/api/portfolio").json()
    assert "cash_balance" in data
    assert "total_value" in data
    assert "total_unrealized_pnl" in data
    assert "positions" in data


# ---------------------------------------------------------------------------
# POST /api/portfolio/trade — buy
# ---------------------------------------------------------------------------


def test_buy_reduces_cash_and_creates_position(client: TestClient) -> None:
    aapl_price = TEST_PRICES["AAPL"]  # 190.00
    qty = 5.0
    cost = aapl_price * qty  # 950.00

    resp = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": qty, "side": "buy"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["trade"]["ticker"] == "AAPL"
    assert data["trade"]["side"] == "buy"
    assert data["trade"]["quantity"] == pytest.approx(qty)
    assert data["trade"]["price"] == pytest.approx(aapl_price)

    portfolio = data["portfolio"]
    assert portfolio["cash_balance"] == pytest.approx(10_000.0 - cost, abs=0.01)

    positions = portfolio["positions"]
    assert len(positions) == 1
    pos = positions[0]
    assert pos["ticker"] == "AAPL"
    assert pos["quantity"] == pytest.approx(qty)
    assert pos["avg_cost"] == pytest.approx(aapl_price)


def test_buy_then_buy_weighted_average_cost(client: TestClient) -> None:
    """Two buys at different (mocked same) prices — weighted avg should still be correct."""
    # First buy: 10 shares at 190
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 10.0, "side": "buy"})
    # Second buy: 10 more shares at same price (cache is fixed)
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 10.0, "side": "buy"})

    resp = client.get("/api/portfolio")
    data = resp.json()
    positions = {p["ticker"]: p for p in data["positions"]}
    assert "AAPL" in positions
    pos = positions["AAPL"]
    # Weighted average: (10*190 + 10*190) / 20 = 190
    assert pos["quantity"] == pytest.approx(20.0)
    assert pos["avg_cost"] == pytest.approx(190.0)
    assert data["cash_balance"] == pytest.approx(10_000.0 - 20 * 190.0, abs=0.01)


def test_buy_fractional_shares(client: TestClient) -> None:
    """Fractional share buy should work correctly."""
    resp = client.post("/api/portfolio/trade", json={"ticker": "MSFT", "quantity": 0.5, "side": "buy"})
    assert resp.status_code == 200
    data = resp.json()
    pos = data["portfolio"]["positions"][0]
    assert pos["quantity"] == pytest.approx(0.5)
    assert pos["avg_cost"] == pytest.approx(TEST_PRICES["MSFT"])


def test_buy_insufficient_cash_returns_400(client: TestClient) -> None:
    """Buying more than cash allows should return 400."""
    # NVDA at 800, buying 100 = $80,000 — way more than $10k
    resp = client.post("/api/portfolio/trade", json={"ticker": "NVDA", "quantity": 100.0, "side": "buy"})
    assert resp.status_code == 400
    assert "Insufficient cash" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /api/portfolio/trade — sell
# ---------------------------------------------------------------------------


def test_sell_reduces_position_and_increases_cash(client: TestClient) -> None:
    aapl_price = TEST_PRICES["AAPL"]
    # Buy 10, then sell 3
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 10.0, "side": "buy"})
    resp = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 3.0, "side": "sell"})
    assert resp.status_code == 200
    data = resp.json()
    portfolio = data["portfolio"]

    positions = {p["ticker"]: p for p in portfolio["positions"]}
    assert "AAPL" in positions
    assert positions["AAPL"]["quantity"] == pytest.approx(7.0)
    # Cash: 10000 - 10*190 + 3*190 = 10000 - 1330 = 8670
    assert portfolio["cash_balance"] == pytest.approx(10_000.0 - 10 * aapl_price + 3 * aapl_price, abs=0.01)


def test_sell_all_deletes_position(client: TestClient) -> None:
    """Selling exact quantity to zero should remove the position row."""
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 5.0, "side": "buy"})
    resp = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 5.0, "side": "sell"})
    assert resp.status_code == 200
    portfolio = resp.json()["portfolio"]
    assert portfolio["positions"] == []


def test_sell_more_than_held_returns_400(client: TestClient) -> None:
    """Selling more shares than held should return 400."""
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 5.0, "side": "buy"})
    resp = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 10.0, "side": "sell"})
    assert resp.status_code == 400
    assert "Insufficient shares" in resp.json()["detail"]


def test_sell_with_no_position_returns_400(client: TestClient) -> None:
    """Selling a ticker with no position should return 400."""
    resp = client.post("/api/portfolio/trade", json={"ticker": "TSLA", "quantity": 1.0, "side": "sell"})
    assert resp.status_code == 400
    assert "Insufficient shares" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


def test_unknown_ticker_no_price_returns_400(client: TestClient) -> None:
    """A ticker not in the cache should return 400."""
    resp = client.post("/api/portfolio/trade", json={"ticker": "ZZZZZ", "quantity": 1.0, "side": "buy"})
    assert resp.status_code == 400
    assert "No market price" in resp.json()["detail"]


def test_invalid_side_returns_422(client: TestClient) -> None:
    """Invalid side value should trigger Pydantic validation (422)."""
    resp = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1.0, "side": "hold"})
    assert resp.status_code == 422


def test_zero_quantity_returns_422(client: TestClient) -> None:
    """Zero quantity should fail Pydantic validation."""
    resp = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 0.0, "side": "buy"})
    assert resp.status_code == 422


def test_negative_quantity_returns_422(client: TestClient) -> None:
    """Negative quantity should fail Pydantic validation."""
    resp = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": -5.0, "side": "buy"})
    assert resp.status_code == 422


def test_ticker_is_normalized(client: TestClient) -> None:
    """Lowercase ticker should be normalized to uppercase."""
    resp = client.post("/api/portfolio/trade", json={"ticker": "aapl", "quantity": 1.0, "side": "buy"})
    assert resp.status_code == 200
    assert resp.json()["trade"]["ticker"] == "AAPL"


# ---------------------------------------------------------------------------
# GET /api/portfolio/history
# ---------------------------------------------------------------------------


def test_portfolio_history_empty_initially(client: TestClient) -> None:
    """No snapshots should exist before any trades."""
    resp = client.get("/api/portfolio/history")
    assert resp.status_code == 200
    assert resp.json() == []


def test_portfolio_history_has_snapshot_after_trade(client: TestClient) -> None:
    """Each trade should create a portfolio snapshot immediately."""
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1.0, "side": "buy"})
    resp = client.get("/api/portfolio/history")
    assert resp.status_code == 200
    snapshots = resp.json()
    assert len(snapshots) >= 1
    snap = snapshots[0]
    assert "recorded_at" in snap
    assert "total_value" in snap
    assert isinstance(snap["total_value"], (int, float))


def test_portfolio_history_multiple_trades_accumulate(client: TestClient) -> None:
    """Multiple trades should produce multiple snapshots."""
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1.0, "side": "buy"})
    client.post("/api/portfolio/trade", json={"ticker": "MSFT", "quantity": 1.0, "side": "buy"})
    resp = client.get("/api/portfolio/history")
    snapshots = resp.json()
    assert len(snapshots) >= 2
