"""Shared fixtures for chat tests."""

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


class StubMarketSource(MarketDataSource):
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


@pytest.fixture()
def mock_mode() -> Generator[None, None, None]:
    """Force LLM_MOCK=true for the duration of the test."""
    old = os.environ.get("LLM_MOCK")
    os.environ["LLM_MOCK"] = "true"
    yield
    if old is None:
        os.environ.pop("LLM_MOCK", None)
    else:
        os.environ["LLM_MOCK"] = old


@pytest.fixture()
def tmp_db_path(tmp_path: Path) -> Generator[Path, None, None]:
    db_file = tmp_path / "chat_finally.db"
    old = os.environ.get("FINALLY_DB_PATH")
    os.environ["FINALLY_DB_PATH"] = str(db_file)
    yield db_file
    if old is None:
        os.environ.pop("FINALLY_DB_PATH", None)
    else:
        os.environ["FINALLY_DB_PATH"] = old


@pytest.fixture()
def test_conn(tmp_db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    conn = get_connection(tmp_db_path)
    init_db(conn)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture()
def test_cache() -> PriceCache:
    cache = PriceCache()
    for ticker, price in TEST_PRICES.items():
        cache.update(ticker, price)
    return cache


@pytest.fixture()
def client(
    mock_mode: None,
    tmp_db_path: Path,
    test_cache: PriceCache,
) -> Generator[TestClient, None, None]:
    """TestClient with chat router wired up, LLM_MOCK enabled, stub market source."""
    from app.chat.router import router as chat_router

    test_app = FastAPI()
    test_app.state.price_cache = test_cache
    source = StubMarketSource()
    test_app.state.market_source = source

    def _test_get_db() -> Generator[sqlite3.Connection, None, None]:
        conn = get_connection(tmp_db_path)
        try:
            yield conn
        finally:
            conn.close()

    test_app.dependency_overrides[get_db] = _test_get_db
    test_app.include_router(chat_router)

    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    loop.run_until_complete(source.start(list(TEST_PRICES.keys())))

    with TestClient(test_app) as c:
        yield c
