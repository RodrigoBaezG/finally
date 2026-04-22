"""Pydantic request/response models for the FinAlly API."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator

# ---------------------------------------------------------------------------
# Portfolio schemas
# ---------------------------------------------------------------------------


class PositionOut(BaseModel):
    """A single open position with live P&L."""

    model_config = ConfigDict(from_attributes=True)

    ticker: str
    quantity: float
    avg_cost: float
    current_price: float
    unrealized_pnl: float
    pnl_percent: float


class PortfolioOut(BaseModel):
    """Full portfolio snapshot returned by GET /api/portfolio."""

    cash_balance: float
    total_value: float
    total_unrealized_pnl: float
    positions: list[PositionOut]


class TradeRequest(BaseModel):
    """Body for POST /api/portfolio/trade."""

    ticker: str
    quantity: float
    side: str

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, v: str) -> str:
        v = v.strip().upper()
        if not v:
            raise ValueError("ticker must not be empty")
        return v

    @field_validator("quantity")
    @classmethod
    def quantity_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("quantity must be greater than 0")
        return v

    @field_validator("side")
    @classmethod
    def side_valid(cls, v: str) -> str:
        v = v.lower()
        if v not in {"buy", "sell"}:
            raise ValueError("side must be 'buy' or 'sell'")
        return v


class TradeOut(BaseModel):
    """Trade record in the trade response."""

    ticker: str
    side: str
    quantity: float
    price: float
    executed_at: str


class TradeResponse(BaseModel):
    """Response from POST /api/portfolio/trade."""

    success: bool
    message: str
    trade: TradeOut | None = None
    portfolio: PortfolioOut | None = None


class SnapshotOut(BaseModel):
    """One portfolio value snapshot."""

    recorded_at: str
    total_value: float


# ---------------------------------------------------------------------------
# Watchlist schemas
# ---------------------------------------------------------------------------


class WatchlistEntryOut(BaseModel):
    """A watchlist ticker with live price data."""

    ticker: str
    price: float
    previous_price: float
    session_start_price: float
    session_change_percent: float
    direction: str


class AddWatchlistRequest(BaseModel):
    """Body for POST /api/watchlist."""

    ticker: str

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, v: str) -> str:
        v = v.strip().upper()
        if not v:
            raise ValueError("ticker must not be empty")
        return v


# ---------------------------------------------------------------------------
# Health schema
# ---------------------------------------------------------------------------


class HealthOut(BaseModel):
    """Response from GET /api/health."""

    status: str
