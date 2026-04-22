"""Tests for watchlist endpoints.

Covers:
- GET /api/watchlist: returns seeded tickers with prices
- POST /api/watchlist: add valid ticker, duplicate 400, unknown 400
- DELETE /api/watchlist/{ticker}: removes ticker, 404 on missing
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import TEST_PRICES

DEFAULT_TICKERS = list(TEST_PRICES.keys())


# ---------------------------------------------------------------------------
# GET /api/watchlist
# ---------------------------------------------------------------------------


def test_watchlist_returns_ten_seeded_tickers(client: TestClient) -> None:
    resp = client.get("/api/watchlist")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 10
    tickers = {item["ticker"] for item in data}
    assert tickers == set(DEFAULT_TICKERS)


def test_watchlist_entry_shape(client: TestClient) -> None:
    """Each entry must have the expected fields."""
    resp = client.get("/api/watchlist")
    entry = resp.json()[0]
    assert "ticker" in entry
    assert "price" in entry
    assert "previous_price" in entry
    assert "session_start_price" in entry
    assert "session_change_percent" in entry
    assert "direction" in entry


def test_watchlist_prices_match_cache(client: TestClient) -> None:
    """Prices must reflect the values seeded in the test cache."""
    resp = client.get("/api/watchlist")
    data = {item["ticker"]: item for item in resp.json()}
    for ticker, expected_price in TEST_PRICES.items():
        assert data[ticker]["price"] == pytest.approx(expected_price)


# ---------------------------------------------------------------------------
# POST /api/watchlist
# ---------------------------------------------------------------------------


def test_add_ticker_already_in_watchlist_returns_400(client: TestClient) -> None:
    """Adding a ticker that is already in the watchlist should return 400."""
    resp = client.post("/api/watchlist", json={"ticker": "AAPL"})
    assert resp.status_code == 400
    assert "Already watching" in resp.json()["detail"]


def test_add_unknown_ticker_returns_400(client: TestClient) -> None:
    """Adding a ticker not in SEED_PRICES should return 400."""
    resp = client.post("/api/watchlist", json={"ticker": "ZZZZZ"})
    assert resp.status_code == 400
    assert "Unknown ticker" in resp.json()["detail"]


def test_add_ticker_response_shape(client: TestClient) -> None:
    """Successful POST should return a WatchlistEntryOut and 201."""
    # First remove a seeded ticker so we can re-add it
    client.delete("/api/watchlist/NFLX")
    resp = client.post("/api/watchlist", json={"ticker": "NFLX"})
    assert resp.status_code == 201
    entry = resp.json()
    assert entry["ticker"] == "NFLX"
    assert "price" in entry
    assert "direction" in entry


def test_add_ticker_lowercase_is_normalized(client: TestClient) -> None:
    """Lowercase ticker in POST body should be normalized."""
    # Remove first so we can re-add
    client.delete("/api/watchlist/TSLA")
    resp = client.post("/api/watchlist", json={"ticker": "tsla"})
    assert resp.status_code == 201
    assert resp.json()["ticker"] == "TSLA"


# ---------------------------------------------------------------------------
# DELETE /api/watchlist/{ticker}
# ---------------------------------------------------------------------------


def test_delete_removes_ticker(client: TestClient) -> None:
    """DELETE should remove the ticker; subsequent GET should not include it."""
    resp = client.delete("/api/watchlist/AAPL")
    assert resp.status_code == 204

    resp = client.get("/api/watchlist")
    tickers = {item["ticker"] for item in resp.json()}
    assert "AAPL" not in tickers


def test_delete_missing_ticker_returns_404(client: TestClient) -> None:
    """Deleting a ticker not in the watchlist should return 404."""
    resp = client.delete("/api/watchlist/ZZZZZ")
    assert resp.status_code == 404


def test_delete_then_add_roundtrip(client: TestClient) -> None:
    """Remove a ticker then add it back — should work cleanly."""
    client.delete("/api/watchlist/GOOGL")
    resp = client.post("/api/watchlist", json={"ticker": "GOOGL"})
    assert resp.status_code == 201

    resp = client.get("/api/watchlist")
    tickers = {item["ticker"] for item in resp.json()}
    assert "GOOGL" in tickers


def test_watchlist_count_changes_after_delete(client: TestClient) -> None:
    """After deleting a ticker, watchlist should have one fewer entry."""
    initial = len(client.get("/api/watchlist").json())
    client.delete("/api/watchlist/META")
    after = len(client.get("/api/watchlist").json())
    assert after == initial - 1
