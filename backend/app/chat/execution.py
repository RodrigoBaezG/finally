"""Auto-execution of trades and watchlist changes requested by the LLM.

Provides execute_trade() and execute_watchlist_change() that work at the
service layer (no HTTP request context required), mirroring the validation
and DB write logic from app.api.portfolio and app.api.watchlist.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass

from app.db import queries
from app.market.cache import PriceCache
from app.market.seed_prices import SEED_PRICES

logger = logging.getLogger(__name__)

_EPSILON = 1e-9


@dataclass
class TradeResult:
    ticker: str
    side: str
    quantity: float
    price: float | None
    status: str  # "executed" | "failed"
    error: str | None


@dataclass
class WatchlistResult:
    ticker: str
    action: str
    status: str  # "executed" | "failed"
    error: str | None


def execute_trade(
    conn: sqlite3.Connection,
    cache: PriceCache,
    ticker: str,
    side: str,
    quantity: float,
    user_id: str = "default",
) -> TradeResult:
    """Execute a single market order, mirroring POST /api/portfolio/trade logic.

    Returns a TradeResult with status="executed" or status="failed".
    Never raises — failures are captured in the result.
    """
    ticker = ticker.strip().upper()
    side = side.strip().lower()

    # Validate side
    if side not in {"buy", "sell"}:
        return TradeResult(
            ticker=ticker,
            side=side,
            quantity=quantity,
            price=None,
            status="failed",
            error=f"Invalid side '{side}': must be 'buy' or 'sell'",
        )

    # Validate quantity
    if quantity <= 0:
        return TradeResult(
            ticker=ticker,
            side=side,
            quantity=quantity,
            price=None,
            status="failed",
            error="Quantity must be positive",
        )

    # Get live price
    price = cache.get_price(ticker)
    if price is None:
        price = SEED_PRICES.get(ticker)
    if price is None:
        return TradeResult(
            ticker=ticker,
            side=side,
            quantity=quantity,
            price=None,
            status="failed",
            error=f"No market price available for {ticker}",
        )

    try:
        profile = queries.get_user_profile(conn, user_id)
        cash_balance = profile["cash_balance"]
        existing_position = queries.get_position(conn, ticker, user_id)

        if side == "buy":
            cost = quantity * price
            if cash_balance < cost:
                return TradeResult(
                    ticker=ticker,
                    side=side,
                    quantity=quantity,
                    price=price,
                    status="failed",
                    error=(
                        f"Insufficient cash: need ${cost:.2f}, "
                        f"have ${cash_balance:.2f}"
                    ),
                )

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
                return TradeResult(
                    ticker=ticker,
                    side=side,
                    quantity=quantity,
                    price=price,
                    status="failed",
                    error=f"No position in {ticker} to sell",
                )
            old_qty = existing_position["quantity"]
            if old_qty < quantity - _EPSILON:
                return TradeResult(
                    ticker=ticker,
                    side=side,
                    quantity=quantity,
                    price=price,
                    status="failed",
                    error=(
                        f"Insufficient shares: trying to sell {quantity}, "
                        f"only have {old_qty}"
                    ),
                )
            new_qty = old_qty - quantity
            avg_cost = existing_position["avg_cost"]
            queries.upsert_position(
                conn,
                ticker,
                new_qty if new_qty > _EPSILON else 0,
                avg_cost,
                user_id,
            )
            queries.update_cash_balance(conn, user_id, cash_balance + quantity * price)

        queries.insert_trade(conn, ticker, side, quantity, price, user_id)

        return TradeResult(
            ticker=ticker,
            side=side,
            quantity=quantity,
            price=price,
            status="executed",
            error=None,
        )

    except Exception as exc:
        logger.exception("Unexpected error executing trade %s %s %s", side, quantity, ticker)
        return TradeResult(
            ticker=ticker,
            side=side,
            quantity=quantity,
            price=price,
            status="failed",
            error=str(exc),
        )


def execute_watchlist_change(
    conn: sqlite3.Connection,
    ticker: str,
    action: str,
    user_id: str = "default",
) -> WatchlistResult:
    """Add or remove a ticker from the watchlist.

    Validates that the ticker exists in SEED_PRICES before adding.
    Returns WatchlistResult with status="executed" or status="failed".
    Never raises.
    """
    ticker = ticker.strip().upper()
    action = action.strip().lower()

    if action not in {"add", "remove"}:
        return WatchlistResult(
            ticker=ticker,
            action=action,
            status="failed",
            error=f"Invalid action '{action}': must be 'add' or 'remove'",
        )

    try:
        if action == "add":
            if ticker not in SEED_PRICES:
                return WatchlistResult(
                    ticker=ticker,
                    action=action,
                    status="failed",
                    error=f"Unknown ticker: {ticker}. Only tickers in the price universe can be added.",
                )
            try:
                queries.add_watchlist_ticker(conn, ticker, user_id)
            except Exception as exc:
                exc_str = str(exc)
                if "UNIQUE" in exc_str.upper() or "unique" in exc_str.lower():
                    return WatchlistResult(
                        ticker=ticker,
                        action=action,
                        status="failed",
                        error=f"{ticker} is already in the watchlist",
                    )
                raise

        else:  # remove
            removed = queries.remove_watchlist_ticker(conn, ticker, user_id)
            if not removed:
                return WatchlistResult(
                    ticker=ticker,
                    action=action,
                    status="failed",
                    error=f"{ticker} is not in the watchlist",
                )

        return WatchlistResult(ticker=ticker, action=action, status="executed", error=None)

    except Exception as exc:
        logger.exception("Unexpected error on watchlist %s %s", action, ticker)
        return WatchlistResult(
            ticker=ticker,
            action=action,
            status="failed",
            error=str(exc),
        )
