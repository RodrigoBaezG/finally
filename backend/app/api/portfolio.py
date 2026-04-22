"""Portfolio endpoints: positions, trades, and history.

Endpoints:
    GET  /api/portfolio          - Current positions, cash balance, total value, P&L
    POST /api/portfolio/trade    - Execute a buy or sell
    GET  /api/portfolio/history  - Portfolio value snapshots over time
"""

from __future__ import annotations

import logging
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request

from app.db import queries
from app.db.connection import get_db
from app.market.cache import PriceCache
from app.market.seed_prices import SEED_PRICES

from .schemas import (
    PortfolioOut,
    PositionOut,
    SnapshotOut,
    TradeOut,
    TradeRequest,
    TradeResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

_EPSILON = 1e-9  # Treat quantities smaller than this as zero


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_cache(request: Request) -> PriceCache:
    return request.app.state.price_cache


def _build_portfolio(
    conn: sqlite3.Connection,
    cache: PriceCache,
    user_id: str = "default",
) -> PortfolioOut:
    """Compute the full portfolio state from DB + live prices."""
    profile = queries.get_user_profile(conn, user_id)
    cash_balance = profile["cash_balance"]

    raw_positions = queries.list_positions(conn, user_id)
    positions: list[PositionOut] = []
    total_market_value = 0.0
    total_unrealized_pnl = 0.0

    for pos in raw_positions:
        ticker = pos["ticker"]
        quantity = pos["quantity"]
        avg_cost = pos["avg_cost"]

        # Live price: fall back to avg_cost if cache miss (keeps math sane)
        current_price = cache.get_price(ticker)
        if current_price is None:
            # Secondary fallback: seed price, then avg_cost
            current_price = SEED_PRICES.get(ticker, avg_cost)

        unrealized_pnl = round((current_price - avg_cost) * quantity, 4)
        pnl_percent = (
            round((current_price - avg_cost) / avg_cost * 100, 4) if avg_cost > 0 else 0.0
        )
        market_value = quantity * current_price
        total_market_value += market_value
        total_unrealized_pnl += unrealized_pnl

        positions.append(
            PositionOut(
                ticker=ticker,
                quantity=round(quantity, 4),
                avg_cost=round(avg_cost, 4),
                current_price=round(current_price, 4),
                unrealized_pnl=unrealized_pnl,
                pnl_percent=pnl_percent,
            )
        )

    total_value = round(cash_balance + total_market_value, 4)

    return PortfolioOut(
        cash_balance=round(cash_balance, 4),
        total_value=total_value,
        total_unrealized_pnl=round(total_unrealized_pnl, 4),
        positions=positions,
    )


def _record_snapshot(
    conn: sqlite3.Connection,
    cache: PriceCache,
    user_id: str = "default",
) -> None:
    """Compute current total value and append a portfolio_snapshots row."""
    portfolio = _build_portfolio(conn, cache, user_id)
    queries.insert_portfolio_snapshot(conn, portfolio.total_value, user_id)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=PortfolioOut)
async def get_portfolio(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
) -> PortfolioOut:
    """Return current positions, cash balance, total value, and unrealized P&L."""
    cache = _get_cache(request)
    return _build_portfolio(conn, cache)


@router.post("/trade", response_model=TradeResponse)
async def execute_trade(
    trade_req: TradeRequest,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
) -> TradeResponse:
    """Execute a market order (buy or sell)."""
    cache = _get_cache(request)
    ticker = trade_req.ticker
    quantity = trade_req.quantity
    side = trade_req.side
    user_id = "default"

    # --- Validate: price must be available ---
    price = cache.get_price(ticker)
    if price is None:
        raise HTTPException(status_code=400, detail=f"No market price for {ticker}")

    # --- Load current state ---
    profile = queries.get_user_profile(conn, user_id)
    cash_balance = profile["cash_balance"]
    existing_position = queries.get_position(conn, ticker, user_id)

    if side == "buy":
        cost = quantity * price
        if cash_balance < cost:
            raise HTTPException(status_code=400, detail="Insufficient cash")

        # Weighted average cost
        if existing_position:
            old_qty = existing_position["quantity"]
            old_avg = existing_position["avg_cost"]
            new_qty = old_qty + quantity
            new_avg = (old_qty * old_avg + quantity * price) / new_qty
        else:
            new_qty = quantity
            new_avg = price

        queries.upsert_position(conn, ticker, new_qty, new_avg, user_id)
        queries.update_cash_balance(conn, user_id, cash_balance - cost)

    else:  # sell
        if existing_position is None:
            raise HTTPException(status_code=400, detail="Insufficient shares")
        old_qty = existing_position["quantity"]
        if old_qty < quantity - _EPSILON:
            raise HTTPException(status_code=400, detail="Insufficient shares")

        new_qty = old_qty - quantity
        # If effectively zero, upsert_position will delete the row
        avg_cost = existing_position["avg_cost"]
        queries.upsert_position(conn, ticker, new_qty if new_qty > _EPSILON else 0, avg_cost, user_id)
        queries.update_cash_balance(conn, user_id, cash_balance + quantity * price)

    # --- Log the trade ---
    trade_row = queries.insert_trade(conn, ticker, side, quantity, price, user_id)

    # --- Immediate portfolio snapshot ---
    _record_snapshot(conn, cache, user_id)

    # --- Build response ---
    portfolio = _build_portfolio(conn, cache, user_id)
    trade_out = TradeOut(
        ticker=trade_row["ticker"],
        side=trade_row["side"],
        quantity=trade_row["quantity"],
        price=trade_row["price"],
        executed_at=trade_row["executed_at"],
    )
    action = "Bought" if side == "buy" else "Sold"
    return TradeResponse(
        success=True,
        message=f"{action} {quantity} share(s) of {ticker} at ${price:.4f}",
        trade=trade_out,
        portfolio=portfolio,
    )


@router.get("/history", response_model=list[SnapshotOut])
async def get_portfolio_history(
    conn: sqlite3.Connection = Depends(get_db),
) -> list[SnapshotOut]:
    """Return portfolio value snapshots over time, oldest first."""
    rows = queries.list_portfolio_snapshots(conn)
    return [SnapshotOut(recorded_at=r["recorded_at"], total_value=r["total_value"]) for r in rows]
