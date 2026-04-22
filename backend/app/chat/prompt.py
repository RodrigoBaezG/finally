"""System prompt and portfolio context builder for FinAlly chat."""

from __future__ import annotations

import json
import sqlite3

from app.db import queries
from app.market.cache import PriceCache
from app.market.seed_prices import SEED_PRICES

SYSTEM_PROMPT = """You are FinAlly, an AI trading assistant embedded in a simulated stock trading workstation.

Your responsibilities:
- Analyze the user's portfolio composition, risk concentration, and unrealized P&L
- Suggest trades with clear, data-driven reasoning
- Execute trades when the user asks or when they agree to your suggestions
- Manage the watchlist proactively (add tickers you reference, remove ones no longer relevant)
- Be concise and data-driven — no unnecessary prose
- Always respond with valid JSON matching the schema below

Response schema (return ONLY this JSON, no markdown fences, no extra text):
{
  "message": "<your conversational reply to the user>",
  "trades": [
    {"ticker": "<TICKER>", "side": "buy" | "sell", "quantity": <number>}
  ],
  "watchlist_changes": [
    {"ticker": "<TICKER>", "action": "add" | "remove"}
  ]
}

Rules:
- "trades" and "watchlist_changes" are optional arrays — include only what applies
- If no trades or watchlist changes, use empty arrays [] or omit the fields
- Quantities must be positive numbers
- Ticker symbols are uppercase (e.g., AAPL, GOOGL)
- You can only trade tickers you have live prices for (shown in portfolio context)
- Never execute a trade the user did not request or approve
- If a user says "buy 5 AAPL", include that trade in the trades array
- If a user says "add PYPL to my watchlist", include that in watchlist_changes
- Keep messages under 200 words unless analysis demands more detail
"""


def build_portfolio_context(
    conn: sqlite3.Connection,
    cache: PriceCache,
    user_id: str = "default",
) -> str:
    """Build a compact portfolio context string to inject into the prompt."""
    profile = queries.get_user_profile(conn, user_id)
    cash_balance = profile["cash_balance"]

    raw_positions = queries.list_positions(conn, user_id)
    positions_data = []
    total_market_value = 0.0

    for pos in raw_positions:
        ticker = pos["ticker"]
        quantity = pos["quantity"]
        avg_cost = pos["avg_cost"]
        current_price = cache.get_price(ticker) or SEED_PRICES.get(ticker, avg_cost)
        unrealized_pnl = round((current_price - avg_cost) * quantity, 2)
        pnl_pct = round((current_price - avg_cost) / avg_cost * 100, 2) if avg_cost > 0 else 0.0
        market_value = round(quantity * current_price, 2)
        total_market_value += market_value
        positions_data.append(
            {
                "ticker": ticker,
                "quantity": round(quantity, 4),
                "avg_cost": round(avg_cost, 2),
                "current_price": round(current_price, 2),
                "unrealized_pnl": unrealized_pnl,
                "pnl_pct": pnl_pct,
                "market_value": market_value,
            }
        )

    total_value = round(cash_balance + total_market_value, 2)

    watchlist_rows = queries.list_watchlist(conn, user_id)
    watchlist_data = []
    for row in watchlist_rows:
        ticker = row["ticker"]
        price = cache.get_price(ticker) or SEED_PRICES.get(ticker, 0.0)
        watchlist_data.append({"ticker": ticker, "price": round(price, 2)})

    context = {
        "cash_balance": round(cash_balance, 2),
        "total_portfolio_value": total_value,
        "positions": positions_data,
        "watchlist": watchlist_data,
    }
    return json.dumps(context, indent=2)
