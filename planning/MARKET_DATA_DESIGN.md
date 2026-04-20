# Market Data Backend — Implementation Design

Implementation-ready design for the FinAlly market data subsystem. Covers the unified interface, in-memory price cache, GBM simulator, Massive API client, SSE streaming endpoint, and FastAPI lifecycle integration.

All code in this document lives under `backend/app/market/`.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [File Structure](#2-file-structure)
3. [Data Model — `models.py`](#3-data-model)
4. [Price Cache — `cache.py`](#4-price-cache)
5. [Abstract Interface — `interface.py`](#5-abstract-interface)
6. [Seed Prices & Ticker Parameters — `seed_prices.py`](#6-seed-prices--ticker-parameters)
7. [GBM Simulator — `simulator.py`](#7-gbm-simulator)
8. [Massive API Client — `massive_client.py`](#8-massive-api-client)
9. [Factory — `factory.py`](#9-factory)
10. [SSE Streaming Endpoint — `stream.py`](#10-sse-streaming-endpoint)
11. [Package Init — `__init__.py`](#11-package-init)
12. [FastAPI Lifecycle Integration](#12-fastapi-lifecycle-integration)
13. [Watchlist Coordination](#13-watchlist-coordination)
14. [Testing Strategy](#14-testing-strategy)
15. [Error Handling & Edge Cases](#15-error-handling--edge-cases)
16. [Configuration Reference](#16-configuration-reference)

---

## 1. Architecture Overview

```
MarketDataSource (ABC)
├── SimulatorDataSource  →  GBM simulator (default, no API key required)
└── MassiveDataSource    →  Polygon.io REST poller (when MASSIVE_API_KEY is set)
        │
        ▼
   PriceCache (thread-safe, in-memory, single source of truth)
        │
        ├──→ SSE stream endpoint  /api/stream/prices  →  Frontend EventSource
        ├──→ Trade execution      /api/portfolio/trade
        └──→ Portfolio valuation  /api/portfolio
```

**Strategy pattern**: both data sources implement the same `MarketDataSource` ABC. All downstream code reads from `PriceCache` without knowing which source produced the data.

**Push model**: data sources write to the cache on their own schedule (500ms for the simulator, 15s for Massive free tier). The SSE endpoint polls the cache every 500ms and pushes changes to connected clients. No coupling between the data source update rate and the SSE send rate.

---

## 2. File Structure

```
backend/
  app/
    market/
      __init__.py             # Re-exports public API
      models.py               # PriceUpdate frozen dataclass
      cache.py                # PriceCache (thread-safe in-memory store)
      interface.py            # MarketDataSource ABC
      seed_prices.py          # SEED_PRICES, TICKER_PARAMS, CORRELATION_GROUPS
      simulator.py            # GBMSimulator + SimulatorDataSource
      massive_client.py       # MassiveDataSource (Polygon.io REST poller)
      factory.py              # create_market_data_source()
      stream.py               # SSE endpoint (FastAPI router factory)
```

Each file has a single responsibility. Downstream code imports from `app.market` — the `__init__.py` is the only public surface.

---

## 3. Data Model

**File: `backend/app/market/models.py`**

`PriceUpdate` is the only data structure that leaves the market data layer. Every downstream consumer works exclusively with this type.

```python
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class PriceUpdate:
    """Immutable snapshot of a single ticker's price at a point in time."""

    ticker: str
    price: float
    previous_price: float
    timestamp: float = field(default_factory=time.time)  # Unix seconds

    @property
    def change(self) -> float:
        """Absolute price change from previous update."""
        return round(self.price - self.previous_price, 4)

    @property
    def change_percent(self) -> float:
        """Percentage change from previous update."""
        if self.previous_price == 0:
            return 0.0
        return round((self.price - self.previous_price) / self.previous_price * 100, 4)

    @property
    def direction(self) -> str:
        """'up', 'down', or 'flat'."""
        if self.price > self.previous_price:
            return "up"
        elif self.price < self.previous_price:
            return "down"
        return "flat"

    def to_dict(self) -> dict:
        """Serialize for JSON / SSE transmission."""
        return {
            "ticker": self.ticker,
            "price": self.price,
            "previous_price": self.previous_price,
            "timestamp": self.timestamp,
            "change": self.change,
            "change_percent": self.change_percent,
            "direction": self.direction,
        }
```

### Design decisions

- **`frozen=True`**: price updates are immutable value objects. Safe to share across async tasks without copying.
- **`slots=True`**: minor memory optimization — the system creates many of these per second.
- **Computed properties** (`change`, `change_percent`, `direction`): derived from stored fields so they can never be inconsistent. No risk of a stale `direction` out of sync with `price`.
- **`to_dict()`**: single serialization point used by both the SSE endpoint and REST responses.

---

## 4. Price Cache

**File: `backend/app/market/cache.py`**

The central data hub. Data sources write to it; SSE streaming and portfolio valuation read from it. Thread-safe because the Massive poller runs synchronous API calls in `asyncio.to_thread()` (a real OS thread), while SSE reads happen on the async event loop.

```python
from __future__ import annotations

import time
from threading import Lock

from .models import PriceUpdate


class PriceCache:
    """Thread-safe in-memory cache of the latest price for each ticker.

    Writers: SimulatorDataSource or MassiveDataSource (one at a time).
    Readers: SSE streaming endpoint, portfolio valuation, trade execution.
    """

    def __init__(self) -> None:
        self._prices: dict[str, PriceUpdate] = {}
        self._lock = Lock()
        self._version: int = 0  # Monotonically increasing; bumped on every write

    def update(self, ticker: str, price: float, timestamp: float | None = None) -> PriceUpdate:
        """Record a new price for a ticker. Returns the created PriceUpdate.

        If this is the first update for the ticker, previous_price == price
        and direction == 'flat'.
        """
        with self._lock:
            ts = timestamp or time.time()
            prev = self._prices.get(ticker)
            previous_price = prev.price if prev else price

            update = PriceUpdate(
                ticker=ticker,
                price=round(price, 2),
                previous_price=round(previous_price, 2),
                timestamp=ts,
            )
            self._prices[ticker] = update
            self._version += 1
            return update

    def get(self, ticker: str) -> PriceUpdate | None:
        """Latest price for a single ticker, or None if unknown."""
        with self._lock:
            return self._prices.get(ticker)

    def get_all(self) -> dict[str, PriceUpdate]:
        """Snapshot of all current prices. Returns a shallow copy."""
        with self._lock:
            return dict(self._prices)

    def get_price(self, ticker: str) -> float | None:
        """Convenience: get just the price float, or None."""
        update = self.get(ticker)
        return update.price if update else None

    def remove(self, ticker: str) -> None:
        """Remove a ticker from the cache (e.g., when removed from watchlist)."""
        with self._lock:
            self._prices.pop(ticker, None)

    @property
    def version(self) -> int:
        """Current version counter. Useful for SSE change detection."""
        return self._version

    def __len__(self) -> int:
        with self._lock:
            return len(self._prices)

    def __contains__(self, ticker: str) -> bool:
        with self._lock:
            return ticker in self._prices
```

### Why a version counter?

The SSE streaming loop polls the cache every 500ms. Without a version counter, it would serialize and push all prices every tick even if nothing changed (e.g., when Massive only updates every 15s). The version counter lets the SSE loop skip sends when nothing is new:

```python
last_version = -1
while True:
    if price_cache.version != last_version:
        last_version = price_cache.version
        yield format_sse(price_cache.get_all())
    await asyncio.sleep(0.5)
```

### Why `threading.Lock` and not `asyncio.Lock`?

The Massive client's synchronous API calls run in `asyncio.to_thread()`, which uses a real OS thread — `asyncio.Lock` would not protect against that. `threading.Lock` works correctly from both sync threads and the async event loop.

---

## 5. Abstract Interface

**File: `backend/app/market/interface.py`**

```python
from __future__ import annotations

from abc import ABC, abstractmethod


class MarketDataSource(ABC):
    """Contract for market data providers.

    Implementations push price updates into a shared PriceCache on their own
    schedule. Downstream code never calls the data source directly for prices —
    it reads from the cache.

    Lifecycle:
        source = create_market_data_source(cache)
        await source.start(["AAPL", "GOOGL", ...])
        # app runs
        await source.add_ticker("TSLA")
        await source.remove_ticker("GOOGL")
        # app shutting down
        await source.stop()
    """

    @abstractmethod
    async def start(self, tickers: list[str]) -> None:
        """Begin producing price updates for the given tickers.

        Seeds the PriceCache with initial prices before the background loop
        starts so that consumers have data immediately.
        Must be called exactly once.
        """

    @abstractmethod
    async def stop(self) -> None:
        """Stop the background task and release resources.

        Safe to call multiple times. After stop(), the source will not write
        to the cache again.
        """

    @abstractmethod
    async def add_ticker(self, ticker: str) -> None:
        """Add a ticker to the active set. No-op if already present.

        For the simulator: also seeds the cache with the initial price.
        For Massive: the ticker appears on the next poll cycle.
        """

    @abstractmethod
    async def remove_ticker(self, ticker: str) -> None:
        """Remove a ticker from the active set. No-op if not present.

        Also removes the ticker from the PriceCache.
        """

    @abstractmethod
    def get_tickers(self) -> list[str]:
        """Return the current list of actively tracked tickers."""
```

### Why the source pushes to cache instead of returning prices

This decouples timing. The simulator ticks every 500ms; Massive polls every 15s. The SSE endpoint reads from the cache at its own 500ms cadence. No part of the system needs to know what the data source's update rate is.

---

## 6. Seed Prices & Ticker Parameters

**File: `backend/app/market/seed_prices.py`**

Constants only — no logic. Shared by the simulator (initial prices, GBM parameters) and by the Massive client (fallback prices before first poll).

```python
"""Seed prices and per-ticker parameters for the market simulator."""

# Realistic starting prices for the default watchlist
SEED_PRICES: dict[str, float] = {
    "AAPL": 190.00,
    "GOOGL": 175.00,
    "MSFT": 420.00,
    "AMZN": 185.00,
    "TSLA": 250.00,
    "NVDA": 800.00,
    "META": 500.00,
    "JPM": 195.00,
    "V": 280.00,
    "NFLX": 600.00,
}

# Per-ticker GBM parameters
# sigma: annualized volatility (higher = more price movement per tick)
# mu: annualized drift / expected return
TICKER_PARAMS: dict[str, dict[str, float]] = {
    "AAPL":  {"sigma": 0.22, "mu": 0.05},
    "GOOGL": {"sigma": 0.25, "mu": 0.05},
    "MSFT":  {"sigma": 0.20, "mu": 0.05},
    "AMZN":  {"sigma": 0.28, "mu": 0.05},
    "TSLA":  {"sigma": 0.50, "mu": 0.03},   # High volatility, low drift
    "NVDA":  {"sigma": 0.40, "mu": 0.08},   # High volatility, strong drift
    "META":  {"sigma": 0.30, "mu": 0.05},
    "JPM":   {"sigma": 0.18, "mu": 0.04},   # Low volatility (bank)
    "V":     {"sigma": 0.17, "mu": 0.04},   # Low volatility (payments)
    "NFLX":  {"sigma": 0.35, "mu": 0.05},
}

# Default parameters for tickers not in the table (dynamically added tickers)
DEFAULT_PARAMS: dict[str, float] = {"sigma": 0.25, "mu": 0.05}

# Sector groups for Cholesky correlation matrix construction
CORRELATION_GROUPS: dict[str, set[str]] = {
    "tech":    {"AAPL", "GOOGL", "MSFT", "AMZN", "META", "NVDA", "NFLX"},
    "finance": {"JPM", "V"},
}

# Pairwise correlation coefficients
INTRA_TECH_CORR    = 0.6   # Tech stocks move together
INTRA_FINANCE_CORR = 0.5   # Finance stocks move together
CROSS_GROUP_CORR   = 0.3   # Between sectors, or for unknown tickers
TSLA_CORR          = 0.3   # TSLA does its own thing, even within tech
```

---

## 7. GBM Simulator

**File: `backend/app/market/simulator.py`**

Two classes with distinct responsibilities:

- `GBMSimulator`: pure math engine. Stateful — holds current prices, advances them one step at a time.
- `SimulatorDataSource`: the `MarketDataSource` implementation that wraps `GBMSimulator` in an async loop and writes to the `PriceCache`.

### 7.1 GBM Math

At each time step, a stock price evolves as:

```
S(t+dt) = S(t) × exp( (mu − sigma²/2) × dt  +  sigma × √dt × Z )
```

Where:
- `S(t)` — current price
- `mu` — annualized drift (expected return), e.g. `0.05` (5%)
- `sigma` — annualized volatility, e.g. `0.22` (22%)
- `dt` — time step as a fraction of a trading year
- `Z` — correlated standard normal random variable

For 500ms ticks over 252 trading days × 6.5 hours/day:
```
dt = 0.5 / (252 × 6.5 × 3600) ≈ 8.5 × 10⁻⁸
```

This tiny `dt` produces sub-cent moves per tick that accumulate naturally over time. Prices can never go negative because `exp()` is always positive.

### 7.2 Correlated Moves via Cholesky Decomposition

Real stocks don't move independently. Given a correlation matrix `C`, compute `L = cholesky(C)`. Then for `n` independent standard normals `z_independent`:

```
z_correlated = L @ z_independent
```

`z_correlated[i]` is then used as the `Z` in the GBM formula for ticker `i`. The result is that tickers in the same sector tend to move in the same direction each tick.

### 7.3 GBMSimulator Implementation

```python
from __future__ import annotations

import asyncio
import logging
import math
import random

import numpy as np

from .cache import PriceCache
from .interface import MarketDataSource
from .seed_prices import (
    CORRELATION_GROUPS,
    CROSS_GROUP_CORR,
    DEFAULT_PARAMS,
    INTRA_FINANCE_CORR,
    INTRA_TECH_CORR,
    SEED_PRICES,
    TICKER_PARAMS,
    TSLA_CORR,
)

logger = logging.getLogger(__name__)


class GBMSimulator:
    """Geometric Brownian Motion simulator for correlated stock prices.

    Math:
        S(t+dt) = S(t) * exp((mu - sigma^2/2) * dt + sigma * sqrt(dt) * Z)

    Where Z is a correlated standard normal, produced by multiplying
    independent normals by the Cholesky decomposition of the correlation matrix.
    """

    # 500ms expressed as a fraction of a trading year
    # 252 trading days * 6.5 hours/day * 3600 seconds/hour = 5,896,800 seconds
    TRADING_SECONDS_PER_YEAR = 252 * 6.5 * 3600
    DEFAULT_DT = 0.5 / TRADING_SECONDS_PER_YEAR   # ~8.48e-8

    def __init__(
        self,
        tickers: list[str],
        dt: float = DEFAULT_DT,
        event_probability: float = 0.001,
    ) -> None:
        self._dt = dt
        self._event_prob = event_probability
        self._tickers: list[str] = []
        self._prices: dict[str, float] = {}
        self._params: dict[str, dict[str, float]] = {}
        self._cholesky: np.ndarray | None = None

        # Initialize all starting tickers without rebuilding Cholesky each time
        for ticker in tickers:
            self._add_ticker_internal(ticker)
        self._rebuild_cholesky()

    # --- Public API ---

    def step(self) -> dict[str, float]:
        """Advance all tickers by one time step. Returns {ticker: new_price}.

        This is the hot path — called every 500ms. Keep it fast.
        """
        n = len(self._tickers)
        if n == 0:
            return {}

        # Generate n independent standard normal draws
        z_independent = np.random.standard_normal(n)

        # Apply Cholesky to get correlated draws
        z_correlated = self._cholesky @ z_independent if self._cholesky is not None else z_independent

        result: dict[str, float] = {}
        for i, ticker in enumerate(self._tickers):
            params = self._params[ticker]
            mu = params["mu"]
            sigma = params["sigma"]

            # GBM: S(t+dt) = S(t) * exp((mu - 0.5*sigma^2)*dt + sigma*sqrt(dt)*Z)
            drift = (mu - 0.5 * sigma ** 2) * self._dt
            diffusion = sigma * math.sqrt(self._dt) * z_correlated[i]
            self._prices[ticker] *= math.exp(drift + diffusion)

            # Random shock: ~0.1% chance per ticker per tick
            # With 10 tickers at 2 ticks/sec, expect an event roughly every 50 seconds
            if random.random() < self._event_prob:
                magnitude = random.uniform(0.02, 0.05)
                direction = random.choice([-1, 1])
                self._prices[ticker] *= 1 + magnitude * direction
                logger.debug(
                    "Shock event on %s: %.1f%% %s",
                    ticker,
                    magnitude * 100,
                    "up" if direction > 0 else "down",
                )

            result[ticker] = round(self._prices[ticker], 2)

        return result

    def add_ticker(self, ticker: str) -> None:
        """Add a ticker. Rebuilds the Cholesky correlation matrix."""
        if ticker in self._prices:
            return
        self._add_ticker_internal(ticker)
        self._rebuild_cholesky()

    def remove_ticker(self, ticker: str) -> None:
        """Remove a ticker. Rebuilds the Cholesky correlation matrix."""
        if ticker not in self._prices:
            return
        self._tickers.remove(ticker)
        del self._prices[ticker]
        del self._params[ticker]
        self._rebuild_cholesky()

    def get_price(self, ticker: str) -> float | None:
        """Current price for a ticker, or None if not tracked."""
        return self._prices.get(ticker)

    def get_tickers(self) -> list[str]:
        """Currently tracked tickers."""
        return list(self._tickers)

    # --- Internals ---

    def _add_ticker_internal(self, ticker: str) -> None:
        """Register a ticker without rebuilding Cholesky (used during batch init)."""
        if ticker in self._prices:
            return
        self._tickers.append(ticker)
        self._prices[ticker] = SEED_PRICES.get(ticker, random.uniform(50.0, 300.0))
        self._params[ticker] = TICKER_PARAMS.get(ticker, dict(DEFAULT_PARAMS))

    def _rebuild_cholesky(self) -> None:
        """Rebuild the Cholesky decomposition from the current ticker list.

        Called whenever tickers are added or removed. O(n²) but n < 50 in practice.
        """
        n = len(self._tickers)
        if n <= 1:
            self._cholesky = None
            return

        corr = np.eye(n)
        for i in range(n):
            for j in range(i + 1, n):
                rho = self._pairwise_correlation(self._tickers[i], self._tickers[j])
                corr[i, j] = rho
                corr[j, i] = rho

        self._cholesky = np.linalg.cholesky(corr)

    @staticmethod
    def _pairwise_correlation(t1: str, t2: str) -> float:
        """Determine the correlation coefficient between two tickers.

        Correlation structure:
          - Same tech sector:     0.6
          - Same finance sector:  0.5
          - TSLA with anything:   0.3  (it does its own thing)
          - Cross-sector:         0.3
          - Unknown tickers:      0.3
        """
        tech = CORRELATION_GROUPS["tech"]
        finance = CORRELATION_GROUPS["finance"]

        if t1 == "TSLA" or t2 == "TSLA":
            return TSLA_CORR
        if t1 in tech and t2 in tech:
            return INTRA_TECH_CORR
        if t1 in finance and t2 in finance:
            return INTRA_FINANCE_CORR
        return CROSS_GROUP_CORR
```

### 7.4 SimulatorDataSource — Async Wrapper

```python
class SimulatorDataSource(MarketDataSource):
    """MarketDataSource backed by the GBM simulator.

    Runs a background asyncio task that calls GBMSimulator.step() every
    `update_interval` seconds and writes results to the PriceCache.
    """

    def __init__(
        self,
        price_cache: PriceCache,
        update_interval: float = 0.5,
        event_probability: float = 0.001,
    ) -> None:
        self._cache = price_cache
        self._interval = update_interval
        self._event_prob = event_probability
        self._sim: GBMSimulator | None = None
        self._task: asyncio.Task | None = None

    async def start(self, tickers: list[str]) -> None:
        self._sim = GBMSimulator(tickers=tickers, event_probability=self._event_prob)

        # Seed the cache with initial prices BEFORE the loop starts.
        # This guarantees the SSE endpoint has data on its very first poll —
        # no blank-screen delay for the user.
        for ticker in tickers:
            price = self._sim.get_price(ticker)
            if price is not None:
                self._cache.update(ticker=ticker, price=price)

        self._task = asyncio.create_task(self._run_loop(), name="simulator-loop")
        logger.info("Simulator started with %d tickers", len(tickers))

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("Simulator stopped")

    async def add_ticker(self, ticker: str) -> None:
        if self._sim:
            self._sim.add_ticker(ticker)
            # Seed cache immediately — the ticker has a valid price right away,
            # not only after the next loop tick.
            price = self._sim.get_price(ticker)
            if price is not None:
                self._cache.update(ticker=ticker, price=price)
            logger.info("Simulator: added ticker %s", ticker)

    async def remove_ticker(self, ticker: str) -> None:
        if self._sim:
            self._sim.remove_ticker(ticker)
        self._cache.remove(ticker)
        logger.info("Simulator: removed ticker %s", ticker)

    def get_tickers(self) -> list[str]:
        return self._sim.get_tickers() if self._sim else []

    async def _run_loop(self) -> None:
        """Core loop: step the simulation, write to cache, sleep."""
        while True:
            try:
                if self._sim:
                    prices = self._sim.step()
                    for ticker, price in prices.items():
                        self._cache.update(ticker=ticker, price=price)
            except Exception:
                logger.exception("Simulator step failed — continuing")
            await asyncio.sleep(self._interval)
```

---

## 8. Massive API Client

**File: `backend/app/market/massive_client.py`**

Polls the Massive (formerly Polygon.io) REST API snapshot endpoint on a configurable interval. The synchronous Massive client runs inside `asyncio.to_thread()` to avoid blocking the event loop.

```python
from __future__ import annotations

import asyncio
import logging
from typing import Any

from .cache import PriceCache
from .interface import MarketDataSource

logger = logging.getLogger(__name__)


class MassiveDataSource(MarketDataSource):
    """MarketDataSource backed by the Massive (Polygon.io) REST API.

    Polls GET /v2/snapshot/locale/us/markets/stocks/tickers for all watched
    tickers in a single API call, then writes results to the PriceCache.

    Rate limits:
      Free tier:  5 req/min  →  poll every 15s (default)
      Paid tiers: unlimited  →  poll every 2-5s is safe
    """

    def __init__(
        self,
        api_key: str,
        price_cache: PriceCache,
        poll_interval: float = 15.0,
    ) -> None:
        self._api_key = api_key
        self._cache = price_cache
        self._interval = poll_interval
        self._tickers: list[str] = []
        self._task: asyncio.Task | None = None
        self._client: Any = None

    async def start(self, tickers: list[str]) -> None:
        from massive import RESTClient

        self._client = RESTClient(api_key=self._api_key)
        self._tickers = list(tickers)

        # Immediate first poll so the cache has data before the loop's first sleep
        await self._poll_once()

        self._task = asyncio.create_task(self._poll_loop(), name="massive-poller")
        logger.info(
            "Massive poller started: %d tickers, %.1fs interval",
            len(tickers),
            self._interval,
        )

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        self._client = None
        logger.info("Massive poller stopped")

    async def add_ticker(self, ticker: str) -> None:
        ticker = ticker.upper().strip()
        if ticker not in self._tickers:
            self._tickers.append(ticker)
            logger.info("Massive: added ticker %s (appears on next poll)", ticker)

    async def remove_ticker(self, ticker: str) -> None:
        ticker = ticker.upper().strip()
        self._tickers = [t for t in self._tickers if t != ticker]
        self._cache.remove(ticker)
        logger.info("Massive: removed ticker %s", ticker)

    def get_tickers(self) -> list[str]:
        return list(self._tickers)

    # --- Internal ---

    async def _poll_loop(self) -> None:
        """Sleep then poll, indefinitely. First poll already happened in start()."""
        while True:
            await asyncio.sleep(self._interval)
            await self._poll_once()

    async def _poll_once(self) -> None:
        """Execute one poll cycle: fetch snapshots from Massive, update cache."""
        if not self._tickers or not self._client:
            return

        try:
            # Massive RESTClient is synchronous — run in a thread to avoid
            # blocking the event loop during the HTTP request.
            snapshots = await asyncio.to_thread(self._fetch_snapshots)

            processed = 0
            for snap in snapshots:
                try:
                    price = snap.last_trade.price
                    # Massive timestamps are Unix milliseconds → convert to seconds
                    timestamp = snap.last_trade.timestamp / 1000.0
                    self._cache.update(ticker=snap.ticker, price=price, timestamp=timestamp)
                    processed += 1
                except (AttributeError, TypeError) as e:
                    logger.warning(
                        "Skipping malformed snapshot for %s: %s",
                        getattr(snap, "ticker", "unknown"),
                        e,
                    )

            logger.debug("Massive poll: updated %d/%d tickers", processed, len(self._tickers))

        except Exception as e:
            logger.error("Massive poll failed: %s", e)
            # Don't re-raise — the loop retries on the next interval.
            # Common failures: 401 (bad key), 429 (rate limit), network errors.

    def _fetch_snapshots(self) -> list:
        """Synchronous Massive REST API call. Runs in asyncio.to_thread()."""
        from massive.rest.models import SnapshotMarketType

        return self._client.get_snapshot_all(
            market_type=SnapshotMarketType.STOCKS,
            tickers=self._tickers,
        )
```

### Massive API response structure

Each snapshot object from `get_snapshot_all` has this shape:

```json
{
  "ticker": "AAPL",
  "last_trade": {
    "price": 190.42,
    "size": 100,
    "timestamp": 1707580800000
  },
  "day": {
    "open": 188.50,
    "high": 191.20,
    "low": 187.80,
    "close": 190.42,
    "volume": 55234100,
    "previous_close": 187.15,
    "change": 3.27,
    "change_percent": 1.75
  }
}
```

We extract `last_trade.price` for the current price and `last_trade.timestamp` (milliseconds) for the timestamp.

### Error handling policy

| Error | Behavior |
|-------|----------|
| **401 Unauthorized** | Logged as error. Poller keeps running (fix key and restart). |
| **429 Rate Limited** | Logged as error. Retries automatically on next interval. |
| **Network timeout** | Logged as error. Retries automatically on next interval. |
| **Malformed snapshot** | Individual ticker skipped with warning; other tickers processed. |
| **All tickers fail** | Cache retains last-known prices. SSE keeps streaming stale-but-valid data. |

### Lazy import rationale

`from massive import RESTClient` happens inside `start()`, not at module import time. This means:
- The `massive` package is only required when `MASSIVE_API_KEY` is set
- Simulator users have zero external dependencies beyond `numpy`
- The import fails loudly at startup (not silently at module load) if the package is missing

---

## 9. Factory

**File: `backend/app/market/factory.py`**

```python
from __future__ import annotations

import logging
import os

from .cache import PriceCache
from .interface import MarketDataSource

logger = logging.getLogger(__name__)


def create_market_data_source(price_cache: PriceCache) -> MarketDataSource:
    """Create the appropriate market data source based on environment variables.

    - MASSIVE_API_KEY set and non-empty → MassiveDataSource (real market data)
    - Otherwise                         → SimulatorDataSource (GBM simulation)

    Returns an unstarted source. Caller must call await source.start(tickers).
    """
    api_key = os.environ.get("MASSIVE_API_KEY", "").strip()

    if api_key:
        from .massive_client import MassiveDataSource
        logger.info("Market data source: Massive API (real data)")
        return MassiveDataSource(api_key=api_key, price_cache=price_cache)
    else:
        from .simulator import SimulatorDataSource
        logger.info("Market data source: GBM Simulator (no MASSIVE_API_KEY)")
        return SimulatorDataSource(price_cache=price_cache)
```

---

## 10. SSE Streaming Endpoint

**File: `backend/app/market/stream.py`**

The SSE endpoint holds open a long-lived HTTP connection and pushes live price updates to the client as `text/event-stream`.

```python
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from .cache import PriceCache

logger = logging.getLogger(__name__)


def create_stream_router(price_cache: PriceCache) -> APIRouter:
    """Factory that creates the SSE streaming router.

    Factory pattern lets us inject the PriceCache without module-level globals.
    """
    router = APIRouter(prefix="/api/stream", tags=["streaming"])

    @router.get("/prices")
    async def stream_prices(request: Request) -> StreamingResponse:
        """SSE endpoint for live price updates.

        Streams all tracked ticker prices every ~500ms. The client connects
        with the native EventSource API and receives JSON-encoded price maps.

        Example event:
            data: {"AAPL": {"ticker": "AAPL", "price": 190.50, ...}, ...}
        """
        return StreamingResponse(
            _generate_events(price_cache, request),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering if behind a proxy
            },
        )

    return router


async def _generate_events(
    price_cache: PriceCache,
    request: Request,
    interval: float = 0.5,
) -> AsyncGenerator[str, None]:
    """Async generator that yields SSE-formatted price events.

    Sends all current prices whenever the cache version changes.
    Stops cleanly when the client disconnects.
    """
    # Tell the client to retry after 1 second on disconnection
    yield "retry: 1000\n\n"

    last_version = -1
    client_ip = request.client.host if request.client else "unknown"
    logger.info("SSE client connected: %s", client_ip)

    try:
        while True:
            if await request.is_disconnected():
                logger.info("SSE client disconnected: %s", client_ip)
                break

            current_version = price_cache.version
            if current_version != last_version:
                last_version = current_version
                prices = price_cache.get_all()

                if prices:
                    payload = json.dumps(
                        {ticker: update.to_dict() for ticker, update in prices.items()}
                    )
                    yield f"data: {payload}\n\n"

            await asyncio.sleep(interval)

    except asyncio.CancelledError:
        logger.info("SSE stream cancelled for: %s", client_ip)
```

### Wire format example

```
retry: 1000

data: {"AAPL":{"ticker":"AAPL","price":190.50,"previous_price":190.42,"timestamp":1707580800.5,"change":0.08,"change_percent":0.042,"direction":"up"},"GOOGL":{"ticker":"GOOGL","price":175.12,"previous_price":175.28,"timestamp":1707580800.5,"change":-0.16,"change_percent":-0.091,"direction":"down"}}

data: {"AAPL":{"ticker":"AAPL","price":190.53,...},...}
```

### Frontend connection

```javascript
const eventSource = new EventSource('/api/stream/prices');

eventSource.onmessage = (event) => {
    // prices: { "AAPL": { ticker, price, previous_price, change, change_percent, direction, timestamp }, ... }
    const prices = JSON.parse(event.data);

    for (const [ticker, update] of Object.entries(prices)) {
        updateWatchlistRow(ticker, update);   // trigger flash animation
        appendToSparkline(ticker, update.price);
    }
};

eventSource.onerror = () => {
    // EventSource handles reconnection automatically using the retry directive
    setConnectionStatus('disconnected');
};

eventSource.onopen = () => {
    setConnectionStatus('connected');
};
```

---

## 11. Package Init

**File: `backend/app/market/__init__.py`**

```python
"""Market data subsystem for FinAlly.

Public API — import from app.market, not from submodules:
    PriceUpdate              - Immutable price snapshot dataclass
    PriceCache               - Thread-safe in-memory price store
    MarketDataSource         - Abstract interface for data providers
    create_market_data_source - Factory: selects simulator or Massive
    create_stream_router      - FastAPI SSE router factory
"""

from .cache import PriceCache
from .factory import create_market_data_source
from .interface import MarketDataSource
from .models import PriceUpdate
from .stream import create_stream_router

__all__ = [
    "PriceUpdate",
    "PriceCache",
    "MarketDataSource",
    "create_market_data_source",
    "create_stream_router",
]
```

---

## 12. FastAPI Lifecycle Integration

The market data system starts and stops with the FastAPI application using the `lifespan` context manager.

**File: `backend/app/main.py`**

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.market import PriceCache, MarketDataSource, create_market_data_source, create_stream_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown of all background services.

    Authoritative startup order:
      1. Initialize SQLite schema; seed default data if needed
      2. Create shared PriceCache
      3. Load watchlist tickers from DB
      4. Start market data source (pre-seeds cache with initial prices)
      5. Register SSE streaming router
      6. Serve requests

    Shutdown: stop the market data source background task.
    """

    # 1. Database init (schema creation + default seed data)
    from app.db import init_db
    await init_db()

    # 2. Shared price cache
    price_cache = PriceCache()
    app.state.price_cache = price_cache

    # 3. Initial tickers from DB watchlist
    from app.db import get_watchlist_tickers
    initial_tickers = await get_watchlist_tickers()

    # 4. Market data source
    source = create_market_data_source(price_cache)
    app.state.market_source = source
    await source.start(initial_tickers)

    # 5. SSE router (registered after source is running)
    app.include_router(create_stream_router(price_cache))

    yield  # Application is live

    # Shutdown
    await source.stop()


app = FastAPI(title="FinAlly API", lifespan=lifespan)


# Dependency helpers for route handlers
def get_price_cache() -> PriceCache:
    return app.state.price_cache


def get_market_source() -> MarketDataSource:
    return app.state.market_source
```

### Dependency injection in route handlers

```python
from fastapi import APIRouter, Depends, HTTPException
from app.main import get_price_cache, get_market_source
from app.market import PriceCache, MarketDataSource

router = APIRouter(prefix="/api")


@router.post("/portfolio/trade")
async def execute_trade(
    trade: TradeRequest,
    price_cache: PriceCache = Depends(get_price_cache),
):
    current_price = price_cache.get_price(trade.ticker)
    if current_price is None:
        raise HTTPException(
            status_code=400,
            detail=f"No price available for {trade.ticker}. Please wait a moment and try again.",
        )
    # ... execute trade at current_price ...


@router.post("/watchlist")
async def add_to_watchlist(
    payload: WatchlistAdd,
    source: MarketDataSource = Depends(get_market_source),
    price_cache: PriceCache = Depends(get_price_cache),
):
    # 1. Validate ticker is known to the data source
    # 2. Insert into DB watchlist
    await db.insert_watchlist_entry(payload.ticker)
    # 3. Start tracking it (for simulator: seeds cache immediately)
    await source.add_ticker(payload.ticker)
    # Return current price (may be None briefly on Massive before first poll)
    return {"ticker": payload.ticker, "price": price_cache.get_price(payload.ticker)}


@router.delete("/watchlist/{ticker}")
async def remove_from_watchlist(
    ticker: str,
    source: MarketDataSource = Depends(get_market_source),
):
    await db.delete_watchlist_entry(ticker)
    # Only stop tracking if no open position (see section 13)
    position = await db.get_position(ticker)
    if position is None or position.quantity == 0:
        await source.remove_ticker(ticker)
    return {"status": "ok"}
```

---

## 13. Watchlist Coordination

### Adding a ticker — full flow

```
POST /api/watchlist {ticker: "PYPL"}
  → Validate ticker is known to the data source
  → Insert into watchlist table (SQLite)
  → await source.add_ticker("PYPL")
      Simulator: adds to GBMSimulator, rebuilds Cholesky, seeds cache immediately
      Massive: appends to internal ticker list; appears on next poll cycle
  → Return {ticker: "PYPL", price: <current or null>}
```

### Removing a ticker — full flow

```
DELETE /api/watchlist/PYPL
  → Delete from watchlist table (SQLite)
  → Check if position exists with quantity > 0
      If yes:  skip source.remove_ticker() — need prices for portfolio valuation
      If no:   await source.remove_ticker("PYPL")
                 → Removes from simulation / poll list
                 → Removes from PriceCache
  → Return {status: "ok"}
```

### Edge case: position exists for removed watchlist ticker

The user removes "PYPL" from the watchlist but still holds shares. The price must remain tracked so portfolio P&L continues to update. The route handler checks:

```python
position = await db.get_position(ticker)
if position is None or position.quantity == 0:
    await source.remove_ticker(ticker)
# else: keep tracking — price still needed for position valuation
```

The ticker stays in the `PriceCache` and data source even though it's no longer in the watchlist DB table. When the user eventually sells the last shares, the portfolio trade handler should call `source.remove_ticker()` if the ticker is also absent from the watchlist.

---

## 14. Testing Strategy

### 14.1 GBMSimulator unit tests

**File: `backend/tests/market/test_simulator.py`**

```python
from app.market.simulator import GBMSimulator
from app.market.seed_prices import SEED_PRICES


class TestGBMSimulator:

    def test_step_returns_all_tickers(self):
        sim = GBMSimulator(tickers=["AAPL", "GOOGL"])
        result = sim.step()
        assert set(result.keys()) == {"AAPL", "GOOGL"}

    def test_prices_are_always_positive(self):
        """GBM prices can never go negative (exp is always positive)."""
        sim = GBMSimulator(tickers=["AAPL"])
        for _ in range(10_000):
            prices = sim.step()
            assert prices["AAPL"] > 0

    def test_initial_prices_match_seeds(self):
        sim = GBMSimulator(tickers=["AAPL"])
        assert sim.get_price("AAPL") == SEED_PRICES["AAPL"]

    def test_add_ticker_appears_in_next_step(self):
        sim = GBMSimulator(tickers=["AAPL"])
        sim.add_ticker("TSLA")
        result = sim.step()
        assert "TSLA" in result

    def test_remove_ticker_absent_from_next_step(self):
        sim = GBMSimulator(tickers=["AAPL", "GOOGL"])
        sim.remove_ticker("GOOGL")
        result = sim.step()
        assert "GOOGL" not in result
        assert "AAPL" in result

    def test_add_duplicate_is_noop(self):
        sim = GBMSimulator(tickers=["AAPL"])
        sim.add_ticker("AAPL")
        assert len(sim.get_tickers()) == 1

    def test_remove_nonexistent_is_noop(self):
        sim = GBMSimulator(tickers=["AAPL"])
        sim.remove_ticker("NOPE")  # Must not raise

    def test_unknown_ticker_gets_random_seed_price(self):
        sim = GBMSimulator(tickers=["ZZZZ"])
        price = sim.get_price("ZZZZ")
        assert 50.0 <= price <= 300.0

    def test_empty_step_returns_empty_dict(self):
        sim = GBMSimulator(tickers=[])
        assert sim.step() == {}

    def test_cholesky_absent_for_single_ticker(self):
        sim = GBMSimulator(tickers=["AAPL"])
        assert sim._cholesky is None

    def test_cholesky_built_for_two_tickers(self):
        sim = GBMSimulator(tickers=["AAPL"])
        sim.add_ticker("GOOGL")
        assert sim._cholesky is not None

    def test_all_10_default_tickers_build_valid_cholesky(self):
        """Full correlation matrix must be positive definite."""
        tickers = list(SEED_PRICES.keys())
        sim = GBMSimulator(tickers=tickers)
        # If Cholesky construction didn't raise, the matrix is valid
        assert sim._cholesky is not None
        result = sim.step()
        assert len(result) == 10
```

### 14.2 PriceCache unit tests

**File: `backend/tests/market/test_cache.py`**

```python
from app.market.cache import PriceCache


class TestPriceCache:

    def test_update_and_get(self):
        cache = PriceCache()
        update = cache.update("AAPL", 190.50)
        assert update.ticker == "AAPL"
        assert update.price == 190.50
        assert cache.get("AAPL") == update

    def test_first_update_is_flat(self):
        cache = PriceCache()
        update = cache.update("AAPL", 190.50)
        assert update.direction == "flat"
        assert update.previous_price == 190.50

    def test_direction_up(self):
        cache = PriceCache()
        cache.update("AAPL", 190.00)
        update = cache.update("AAPL", 191.00)
        assert update.direction == "up"
        assert update.change == 1.00

    def test_direction_down(self):
        cache = PriceCache()
        cache.update("AAPL", 190.00)
        update = cache.update("AAPL", 189.00)
        assert update.direction == "down"
        assert update.change == -1.00

    def test_remove_clears_ticker(self):
        cache = PriceCache()
        cache.update("AAPL", 190.00)
        cache.remove("AAPL")
        assert cache.get("AAPL") is None

    def test_remove_nonexistent_is_noop(self):
        cache = PriceCache()
        cache.remove("NOPE")  # Must not raise

    def test_get_all_returns_copy(self):
        cache = PriceCache()
        cache.update("AAPL", 190.00)
        cache.update("GOOGL", 175.00)
        snapshot = cache.get_all()
        assert set(snapshot.keys()) == {"AAPL", "GOOGL"}

    def test_version_increments_on_each_write(self):
        cache = PriceCache()
        v0 = cache.version
        cache.update("AAPL", 190.00)
        assert cache.version == v0 + 1
        cache.update("AAPL", 191.00)
        assert cache.version == v0 + 2

    def test_version_unchanged_without_writes(self):
        cache = PriceCache()
        v0 = cache.version
        _ = cache.get_all()
        assert cache.version == v0

    def test_get_price_convenience(self):
        cache = PriceCache()
        cache.update("AAPL", 190.50)
        assert cache.get_price("AAPL") == 190.50
        assert cache.get_price("NOPE") is None
```

### 14.3 SimulatorDataSource integration tests

**File: `backend/tests/market/test_simulator_source.py`**

```python
import asyncio
import pytest
from app.market.cache import PriceCache
from app.market.simulator import SimulatorDataSource


@pytest.mark.asyncio
class TestSimulatorDataSource:

    async def test_start_seeds_cache_immediately(self):
        """Cache must have prices BEFORE the first loop tick."""
        cache = PriceCache()
        source = SimulatorDataSource(price_cache=cache, update_interval=60.0)
        await source.start(["AAPL", "GOOGL"])
        # No sleep needed — seeding happens synchronously in start()
        assert cache.get("AAPL") is not None
        assert cache.get("GOOGL") is not None
        await source.stop()

    async def test_prices_update_after_loop_ticks(self):
        cache = PriceCache()
        source = SimulatorDataSource(price_cache=cache, update_interval=0.05)
        await source.start(["AAPL"])
        v0 = cache.version
        await asyncio.sleep(0.3)  # Allow several ticks
        assert cache.version > v0
        await source.stop()

    async def test_stop_is_idempotent(self):
        cache = PriceCache()
        source = SimulatorDataSource(price_cache=cache, update_interval=0.1)
        await source.start(["AAPL"])
        await source.stop()
        await source.stop()  # Second stop must not raise

    async def test_add_ticker_seeds_cache_immediately(self):
        cache = PriceCache()
        source = SimulatorDataSource(price_cache=cache, update_interval=60.0)
        await source.start(["AAPL"])
        await source.add_ticker("TSLA")
        assert "TSLA" in source.get_tickers()
        assert cache.get("TSLA") is not None
        await source.stop()

    async def test_remove_ticker_clears_cache(self):
        cache = PriceCache()
        source = SimulatorDataSource(price_cache=cache, update_interval=60.0)
        await source.start(["AAPL", "TSLA"])
        await source.remove_ticker("TSLA")
        assert "TSLA" not in source.get_tickers()
        assert cache.get("TSLA") is None
        await source.stop()
```

### 14.4 MassiveDataSource tests (with mocks)

**File: `backend/tests/market/test_massive.py`**

```python
from unittest.mock import MagicMock, patch
import pytest
from app.market.cache import PriceCache
from app.market.massive_client import MassiveDataSource


def make_snapshot(ticker: str, price: float, timestamp_ms: int) -> MagicMock:
    snap = MagicMock()
    snap.ticker = ticker
    snap.last_trade.price = price
    snap.last_trade.timestamp = timestamp_ms
    return snap


@pytest.mark.asyncio
class TestMassiveDataSource:

    async def test_poll_updates_cache(self):
        cache = PriceCache()
        source = MassiveDataSource(api_key="test-key", price_cache=cache, poll_interval=60.0)
        source._client = MagicMock()
        source._tickers = ["AAPL", "GOOGL"]

        mock_snaps = [
            make_snapshot("AAPL", 190.50, 1707580800000),
            make_snapshot("GOOGL", 175.25, 1707580800000),
        ]
        with patch.object(source, "_fetch_snapshots", return_value=mock_snaps):
            await source._poll_once()

        assert cache.get_price("AAPL") == 190.50
        assert cache.get_price("GOOGL") == 175.25

    async def test_malformed_snapshot_is_skipped(self):
        cache = PriceCache()
        source = MassiveDataSource(api_key="test-key", price_cache=cache, poll_interval=60.0)
        source._client = MagicMock()
        source._tickers = ["AAPL", "BAD"]

        good = make_snapshot("AAPL", 190.50, 1707580800000)
        bad = MagicMock()
        bad.ticker = "BAD"
        bad.last_trade = None  # Will raise AttributeError when accessed

        with patch.object(source, "_fetch_snapshots", return_value=[good, bad]):
            await source._poll_once()

        assert cache.get_price("AAPL") == 190.50
        assert cache.get_price("BAD") is None

    async def test_api_error_does_not_crash(self):
        """The loop must survive a complete API failure."""
        cache = PriceCache()
        source = MassiveDataSource(api_key="test-key", price_cache=cache, poll_interval=60.0)
        source._client = MagicMock()
        source._tickers = ["AAPL"]

        with patch.object(source, "_fetch_snapshots", side_effect=Exception("network error")):
            await source._poll_once()  # Must not raise

        assert cache.get_price("AAPL") is None  # No update happened

    async def test_add_and_remove_ticker(self):
        cache = PriceCache()
        source = MassiveDataSource(api_key="test-key", price_cache=cache, poll_interval=60.0)
        source._client = MagicMock()
        source._tickers = ["AAPL"]

        await source.add_ticker("TSLA")
        assert "TSLA" in source.get_tickers()

        cache.update("TSLA", 250.00)  # Simulate a prior update
        await source.remove_ticker("TSLA")
        assert "TSLA" not in source.get_tickers()
        assert cache.get("TSLA") is None

    async def test_timestamp_converted_from_ms_to_seconds(self):
        cache = PriceCache()
        source = MassiveDataSource(api_key="test-key", price_cache=cache, poll_interval=60.0)
        source._client = MagicMock()
        source._tickers = ["AAPL"]

        timestamp_ms = 1707580800000
        snap = make_snapshot("AAPL", 190.00, timestamp_ms)
        with patch.object(source, "_fetch_snapshots", return_value=[snap]):
            await source._poll_once()

        update = cache.get("AAPL")
        assert update is not None
        assert abs(update.timestamp - timestamp_ms / 1000.0) < 0.001
```

### 14.5 Factory tests

**File: `backend/tests/market/test_factory.py`**

```python
import os
from unittest.mock import patch
from app.market.cache import PriceCache
from app.market.factory import create_market_data_source
from app.market.simulator import SimulatorDataSource
from app.market.massive_client import MassiveDataSource


class TestFactory:

    def test_no_api_key_returns_simulator(self):
        cache = PriceCache()
        with patch.dict(os.environ, {}, clear=True):
            source = create_market_data_source(cache)
        assert isinstance(source, SimulatorDataSource)

    def test_empty_api_key_returns_simulator(self):
        cache = PriceCache()
        with patch.dict(os.environ, {"MASSIVE_API_KEY": ""}):
            source = create_market_data_source(cache)
        assert isinstance(source, SimulatorDataSource)

    def test_whitespace_api_key_returns_simulator(self):
        cache = PriceCache()
        with patch.dict(os.environ, {"MASSIVE_API_KEY": "   "}):
            source = create_market_data_source(cache)
        assert isinstance(source, SimulatorDataSource)

    def test_valid_api_key_returns_massive(self):
        cache = PriceCache()
        with patch.dict(os.environ, {"MASSIVE_API_KEY": "pk_test_key"}):
            source = create_market_data_source(cache)
        assert isinstance(source, MassiveDataSource)
```

---

## 15. Error Handling & Edge Cases

### Empty watchlist at startup

If the database watchlist is empty (user deleted everything), `start()` receives `[]`. Both data sources handle this gracefully — the simulator produces no prices, Massive skips its poll. The SSE endpoint sends empty events. When the user adds a ticker, the source starts tracking it immediately.

### Price cache miss during trade

If a ticker has no cached price (e.g., just added to watchlist, Massive hasn't polled yet):

```python
price = price_cache.get_price(ticker)
if price is None:
    raise HTTPException(
        status_code=400,
        detail=f"Price not yet available for {ticker}. Please wait a moment.",
    )
```

The simulator avoids this scenario by seeding the cache synchronously in `add_ticker()`. Massive may have a brief gap — the HTTP 400 with a clear message is the correct user-facing response.

### Massive API key invalid or missing

If `MASSIVE_API_KEY` is set but invalid (401) or rate-limited (429), the poller logs the error and keeps retrying on every interval. The SSE endpoint streams whatever stale prices are in the cache. The user sees prices from the last successful poll; the connection status indicator stays green (SSE is working). The fix is to correct the key in `.env` and restart.

### Ticker removed while position is held

Covered in section 13. The route handler checks for an open position before calling `source.remove_ticker()`. If a position exists, the ticker stays in the tracking set even though it's gone from the watchlist table.

### Thread safety under load

`PriceCache` uses `threading.Lock` — one lock holder at a time. With 10 tickers at 2 updates/second, lock contention is negligible. The critical section is a single dict assignment.

### Simulator numerical stability

GBM with `exp()` is numerically stable and always produces positive prices. Prices are `round()`ed to 2 decimal places in `GBMSimulator.step()`. The tiny `dt` (~8.5e-8) prevents unrealistically large per-tick moves even at high volatility.

---

## 16. Configuration Reference

| Parameter | Location | Default | Description |
|-----------|----------|---------|-------------|
| `MASSIVE_API_KEY` | Environment variable | `""` (empty) | If set and non-empty, use Massive API; otherwise use simulator |
| `update_interval` | `SimulatorDataSource.__init__` | `0.5` s | Time between simulator ticks |
| `poll_interval` | `MassiveDataSource.__init__` | `15.0` s | Time between Massive API polls (free tier: 5 req/min) |
| `event_probability` | `GBMSimulator.__init__` | `0.001` | Per-ticker per-tick probability of a random shock (2–5% move) |
| `dt` | `GBMSimulator.__init__` | `~8.5e-8` | GBM time step (fraction of a trading year) |
| SSE push interval | `_generate_events()` | `0.5` s | How often the SSE loop checks for cache changes |
| SSE retry directive | `_generate_events()` | `1000` ms | Browser EventSource reconnect delay |

### `pyproject.toml` required configuration

```toml
[tool.hatch.build.targets.wheel]
packages = ["app"]
```

Without this, `uv sync` cannot determine which files to include in the wheel and will fail with a `ValueError`. This must be present before running Docker builds.

### Dependencies

```toml
[project]
dependencies = [
    "fastapi",
    "uvicorn",
    "numpy",        # Required for GBM simulator (Cholesky decomposition)
    "massive>=1.0.0",  # Required only when MASSIVE_API_KEY is set; lazy-imported
]
```
