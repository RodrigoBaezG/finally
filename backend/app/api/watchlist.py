"""Watchlist endpoints: list, add, and remove tickers.

Endpoints:
    GET    /api/watchlist          - Current watchlist with live prices
    POST   /api/watchlist          - Add a ticker
    DELETE /api/watchlist/{ticker} - Remove a ticker
"""

from __future__ import annotations

import logging
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from app.db import queries
from app.db.connection import get_db
from app.market.cache import PriceCache
from app.market.seed_prices import SEED_PRICES

from .schemas import AddWatchlistRequest, WatchlistEntryOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_cache(request: Request) -> PriceCache:
    return request.app.state.price_cache


def _build_watchlist_entry(ticker: str, cache: PriceCache) -> WatchlistEntryOut:
    """Build a watchlist entry from cache; fall back to seed price if needed."""
    update = cache.get(ticker)
    if update is not None:
        return WatchlistEntryOut(
            ticker=ticker,
            price=round(update.price, 4),
            previous_price=round(update.previous_price, 4),
            session_start_price=round(update.session_start_price, 4),
            session_change_percent=round(update.session_change_percent, 4),
            direction=update.direction,
        )

    # Cache miss — use seed price as a static fallback
    seed = SEED_PRICES.get(ticker, 0.0)
    return WatchlistEntryOut(
        ticker=ticker,
        price=round(seed, 4),
        previous_price=round(seed, 4),
        session_start_price=round(seed, 4),
        session_change_percent=0.0,
        direction="flat",
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=list[WatchlistEntryOut])
async def get_watchlist(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
) -> list[WatchlistEntryOut]:
    """Return all watched tickers with their latest prices."""
    cache = _get_cache(request)
    rows = queries.list_watchlist(conn)
    return [_build_watchlist_entry(row["ticker"], cache) for row in rows]


@router.post("", response_model=WatchlistEntryOut, status_code=201)
async def add_watchlist_ticker(
    body: AddWatchlistRequest,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
) -> WatchlistEntryOut:
    """Add a ticker to the watchlist.

    Returns 400 if the ticker is not known to the price source.
    Returns 400 if the ticker is already in the watchlist.
    """
    ticker = body.ticker
    cache = _get_cache(request)

    # Validate: ticker must be known to the price source
    if ticker not in SEED_PRICES:
        raise HTTPException(status_code=400, detail=f"Unknown ticker: {ticker}")

    # Insert into DB — raises IntegrityError on duplicate
    try:
        queries.add_watchlist_ticker(conn, ticker)
    except Exception as exc:
        # sqlite3.IntegrityError for duplicate (user_id, ticker) unique constraint
        if "UNIQUE" in str(exc).upper() or "unique" in str(exc).lower():
            raise HTTPException(status_code=400, detail="Already watching") from exc
        raise

    # Sync the market source so the new ticker gets priced next tick
    await _sync_market_source(request)

    return _build_watchlist_entry(ticker, cache)


@router.delete("/{ticker}", status_code=204)
async def remove_watchlist_ticker(
    ticker: str,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
) -> Response:
    """Remove a ticker from the watchlist.

    Returns 404 if the ticker was not in the watchlist.
    """
    ticker = ticker.strip().upper()
    removed = queries.remove_watchlist_ticker(conn, ticker)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Ticker not in watchlist: {ticker}")

    # Sync the market source so removed ticker stops being priced
    await _sync_market_source(request)

    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Sync helper (called after mutations)
# ---------------------------------------------------------------------------


async def _sync_market_source(request: Request) -> None:
    """Diff DB watchlist vs source tickers and call add/remove as needed."""
    from app.main import sync_market_source_tickers  # avoid circular import at module load

    await sync_market_source_tickers(request.app)
