"""Shared fixtures for API endpoint tests.

Uses a temporary SQLite database (via FINALLY_DB_PATH env var) and a
pre-populated PriceCache with known seed prices — no real simulator runs.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.connection import get_connection, get_db, init_db
from app.market.cache import PriceCache
from app.market.interface import MarketDataSource

# ---------------------------------------------------------------------------
# Stub market source — no GBM, no background task
# ---------------------------------------------------------------------------


class StubMarketSource(MarketDataSource):
    """Synchronous stub that never spawns background tasks."""

    def __init__(self) -> None:
        self._tickers: list[str] = []

    async def start(self, tickers: list[str]) -> None:
        self._tickers = list(tickers)

    async def stop(self) -> None:
        pass

    async def add_ticker(self, ticker: str) -> None:
        if ticker not in self._tickers:
            self._tickers.append(ticker)

    async def remove_ticker(self, ticker: str) -> None:
        if ticker in self._tickers:
            self._tickers.remove(ticker)

    def get_tickers(self) -> list[str]:
        return list(self._tickers)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


# Known tickers available in the test cache
TEST_PRICES: dict[str, float] = {
    "AAPL": 190.00,
    "MSFT": 420.00,
    "TSLA": 250.00,
    "GOOGL": 175.00,
    "AMZN": 185.00,
    "NVDA": 800.00,
    "META": 500.00,
    "JPM": 195.00,
    "V": 280.00,
    "NFLX": 600.00,
}


def _make_test_cache() -> PriceCache:
    """Build a PriceCache pre-seeded with TEST_PRICES."""
    cache = PriceCache()
    for ticker, price in TEST_PRICES.items():
        cache.update(ticker, price)
    return cache


@pytest.fixture()
def tmp_db_path(tmp_path: Path) -> Generator[Path, None, None]:
    """Yield a temporary DB path and set FINALLY_DB_PATH for the duration."""
    db_file = tmp_path / "test_finally.db"
    old = os.environ.get("FINALLY_DB_PATH")
    os.environ["FINALLY_DB_PATH"] = str(db_file)
    yield db_file
    if old is None:
        os.environ.pop("FINALLY_DB_PATH", None)
    else:
        os.environ["FINALLY_DB_PATH"] = old


@pytest.fixture()
def test_conn(tmp_db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    """Yield an initialized SQLite connection to the temp database."""
    conn = get_connection(tmp_db_path)
    init_db(conn)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture()
def test_cache() -> PriceCache:
    """Return a PriceCache with known prices for all default tickers."""
    return _make_test_cache()


@pytest.fixture()
def test_source() -> StubMarketSource:
    """Return a stub market source seeded with default tickers."""
    source = StubMarketSource()
    return source


@pytest.fixture()
def client(tmp_db_path: Path, test_cache: PriceCache, test_source: StubMarketSource) -> Generator[TestClient, None, None]:
    """Build a TestClient with dependency overrides for DB and market state.

    - DB: connects to the temporary database
    - PriceCache / MarketSource: injected via app.state (no real simulator)
    - Background snapshot task: not started
    - Static file mount: skipped (no static/ directory in tests)
    """
    # Build a minimal FastAPI app that mirrors production routing
    # but skips the lifespan (no simulator, no snapshot task).

    from app.api.health import router as health_router
    from app.api.portfolio import router as portfolio_router
    from app.api.watchlist import router as watchlist_router

    test_app = FastAPI()

    # Pre-populate state so dependencies can read from it
    test_app.state.price_cache = test_cache
    test_app.state.market_source = test_source

    # Override the get_db dependency to use the temp DB
    def _test_get_db() -> Generator[sqlite3.Connection, None, None]:
        conn = get_connection(tmp_db_path)
        try:
            yield conn
        finally:
            conn.close()

    test_app.dependency_overrides[get_db] = _test_get_db

    test_app.include_router(health_router)
    test_app.include_router(portfolio_router)
    test_app.include_router(watchlist_router)

    # Seed the stub source with default tickers
    import asyncio
    default_tickers = list(TEST_PRICES.keys())
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    loop.run_until_complete(test_source.start(default_tickers))

    with TestClient(test_app) as c:
        yield c
