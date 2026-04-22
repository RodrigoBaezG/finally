"""FastAPI router for the chat endpoint."""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.chat.service import handle_chat
from app.db.connection import get_db
from app.market.cache import PriceCache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


class TradeAction(BaseModel):
    ticker: str
    side: str
    quantity: float
    price: float | None = None
    status: str
    error: str | None = None


class WatchlistAction(BaseModel):
    ticker: str
    action: str
    status: str
    error: str | None = None


class ChatResponse(BaseModel):
    message: str
    trades: list[TradeAction] = []
    watchlist_changes: list[WatchlistAction] = []


def _get_cache(request: Request) -> PriceCache:
    return request.app.state.price_cache


@router.post("", response_model=ChatResponse)
async def post_chat(
    chat_req: ChatRequest,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
) -> ChatResponse:
    """Process a user chat message and return the assistant's structured reply.

    The LLM may auto-execute trades and watchlist changes. Successfully
    executed actions are persisted; failed attempts are only surfaced in
    the response (and described in the assistant's `message`).
    """
    cache = _get_cache(request)

    result: dict[str, Any] = handle_chat(
        conn=conn,
        cache=cache,
        user_message=chat_req.message,
    )

    # If any watchlist changes were executed, sync the market source so
    # new tickers start streaming prices (and removed ones stop).
    if any(c.get("status") == "executed" for c in result.get("watchlist_changes", [])):
        try:
            from app.main import sync_market_source_tickers

            await sync_market_source_tickers(request.app)
        except Exception:
            logger.exception("Failed to sync market source tickers after chat")

    return ChatResponse(**result)
