"""Deterministic mock LLM for FinAlly — used when LLM_MOCK=true.

Parses the user message with simple keyword matching and returns a
structured response in the same shape the real LLM would produce. This
lets E2E tests exercise the full auto-execution code path without
hitting the network.
"""

from __future__ import annotations

import re
from typing import Any

# Regex for quantities — accepts ints or decimals. Defaults to 1 if absent.
_QTY_PATTERN = r"(?:(\d+(?:\.\d+)?)\s+)?"
_TICKER_PATTERN = r"([A-Z]{1,6})"


_BUY_RE = re.compile(
    rf"\b(?:buy|purchase|long)\s+{_QTY_PATTERN}(?:shares?\s+of\s+)?{_TICKER_PATTERN}\b",
    re.IGNORECASE,
)
_SELL_RE = re.compile(
    rf"\b(?:sell|dump|short)\s+{_QTY_PATTERN}(?:shares?\s+of\s+)?{_TICKER_PATTERN}\b",
    re.IGNORECASE,
)
_ADD_WATCH_RE = re.compile(
    rf"\b(?:add|watch|track)\s+{_TICKER_PATTERN}(?:\s+to\s+(?:my\s+)?watchlist)?\b",
    re.IGNORECASE,
)
_REMOVE_WATCH_RE = re.compile(
    rf"\b(?:remove|drop|untrack|stop\s+watching)\s+{_TICKER_PATTERN}"
    r"(?:\s+from\s+(?:my\s+)?watchlist)?\b",
    re.IGNORECASE,
)


def _extract_ticker_from_add(text: str) -> str | None:
    m = _ADD_WATCH_RE.search(text)
    if not m:
        return None
    return m.group(1).upper()


def _extract_ticker_from_remove(text: str) -> str | None:
    m = _REMOVE_WATCH_RE.search(text)
    if not m:
        return None
    return m.group(1).upper()


def _looks_like_portfolio_query(text: str) -> bool:
    lowered = text.lower()
    return any(
        kw in lowered
        for kw in (
            "portfolio",
            "analyze",
            "positions",
            "holdings",
            "balance",
            "how am i doing",
            "pnl",
            "p&l",
        )
    )


def _summarize_portfolio(context: dict[str, Any]) -> str:
    cash = context.get("cash_balance", 0.0)
    total = context.get("total_portfolio_value", cash)
    positions = context.get("positions", []) or []

    if not positions:
        return (
            f"You have ${cash:,.2f} in cash and no open positions "
            f"(total portfolio value: ${total:,.2f}). "
            "Consider starting with a few diversified positions."
        )

    lines = [
        f"Portfolio value: ${total:,.2f} (cash ${cash:,.2f}).",
        f"Open positions: {len(positions)}.",
    ]
    for pos in positions[:5]:
        lines.append(
            f" - {pos['ticker']}: {pos['quantity']} @ avg ${pos['avg_cost']:.2f}"
            f" | now ${pos['current_price']:.2f}"
            f" | P&L ${pos['unrealized_pnl']:.2f} ({pos['pnl_pct']:+.2f}%)"
        )
    return "\n".join(lines)


def generate_mock_response(user_message: str, portfolio_context: dict[str, Any]) -> dict:
    """Return a structured LLM-style response based on keyword matching.

    Shape matches what the real LLM path produces after parsing:
        {"message": str, "trades": [...], "watchlist_changes": [...]}
    """
    text = user_message.strip()
    trades: list[dict] = []
    watchlist_changes: list[dict] = []
    message_parts: list[str] = []

    # Buy
    for m in _BUY_RE.finditer(text):
        qty_str, ticker = m.group(1), m.group(2)
        qty = float(qty_str) if qty_str else 1.0
        trades.append({"ticker": ticker.upper(), "side": "buy", "quantity": qty})

    # Sell
    for m in _SELL_RE.finditer(text):
        qty_str, ticker = m.group(1), m.group(2)
        qty = float(qty_str) if qty_str else 1.0
        trades.append({"ticker": ticker.upper(), "side": "sell", "quantity": qty})

    # Watchlist add — only if the add regex matches and no buy/sell claims the ticker
    ticker = _extract_ticker_from_add(text)
    if ticker:
        already_traded = any(t["ticker"] == ticker for t in trades)
        if not already_traded:
            watchlist_changes.append({"ticker": ticker, "action": "add"})

    # Watchlist remove
    rticker = _extract_ticker_from_remove(text)
    if rticker:
        watchlist_changes.append({"ticker": rticker, "action": "remove"})

    # Compose message
    if trades:
        trade_descs = [
            f"{t['side']}ing {t['quantity']} share(s) of {t['ticker']}" for t in trades
        ]
        message_parts.append(f"Executing: {', '.join(trade_descs)}.")

    if watchlist_changes:
        wl_descs = [f"{c['action']} {c['ticker']}" for c in watchlist_changes]
        message_parts.append(f"Watchlist: {', '.join(wl_descs)}.")

    if not trades and not watchlist_changes:
        if _looks_like_portfolio_query(text):
            message_parts.append(_summarize_portfolio(portfolio_context))
        else:
            # Default greeting
            message_parts.append(
                "Hi — I'm FinAlly, your AI trading assistant. "
                "Ask me about your portfolio, or tell me to buy/sell shares "
                "or manage your watchlist."
            )

    return {
        "message": " ".join(message_parts),
        "trades": trades,
        "watchlist_changes": watchlist_changes,
    }
