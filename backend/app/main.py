"""FinAlly FastAPI application entrypoint.

Run with:
    cd backend
    uv run uvicorn app.main:app --port 8000
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.db import queries
from app.db.connection import get_connection, init_db
from app.market import PriceCache, create_market_data_source, create_stream_router

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Snapshot background task
# ---------------------------------------------------------------------------


async def _snapshot_loop(app: FastAPI) -> None:
    """Record portfolio value every 30 seconds."""
    while True:
        try:
            await asyncio.sleep(30)
            conn = get_connection()
            try:
                cache: PriceCache = app.state.price_cache
                from app.api.portfolio import _record_snapshot  # local import avoids cycle

                _record_snapshot(conn, cache)
                logger.debug("Portfolio snapshot recorded")
            finally:
                conn.close()
        except asyncio.CancelledError:
            logger.info("Snapshot task cancelled — shutting down")
            raise
        except Exception:
            logger.exception("Snapshot task error (will retry in 30s)")


# ---------------------------------------------------------------------------
# Sync helper: keep market source tickers aligned with DB watchlist
# ---------------------------------------------------------------------------


async def sync_market_source_tickers(app: FastAPI) -> None:
    """Diff DB watchlist against market source tickers and reconcile.

    Adds tickers present in DB but not in source; removes tickers present in
    source but not in DB. Safe to call after any watchlist mutation.
    """
    source = app.state.market_source
    conn = get_connection()
    try:
        db_rows = queries.list_watchlist(conn)
        db_tickers = {row["ticker"] for row in db_rows}
        source_tickers = set(source.get_tickers())

        for ticker in db_tickers - source_tickers:
            logger.info("Adding ticker to market source: %s", ticker)
            await source.add_ticker(ticker)

        for ticker in source_tickers - db_tickers:
            logger.info("Removing ticker from market source: %s", ticker)
            await source.remove_ticker(ticker)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Initialize database
    conn = get_connection()
    try:
        init_db(conn)
        initial_tickers = [row["ticker"] for row in queries.list_watchlist(conn)]
    finally:
        conn.close()

    logger.info("Database initialized. Watchlist: %s", initial_tickers)

    # Initialize market data
    cache = PriceCache()
    source = create_market_data_source(cache)
    await source.start(initial_tickers)

    app.state.price_cache = cache
    app.state.market_source = source

    logger.info("Market data source started with %d tickers", len(initial_tickers))

    # Start background snapshot task
    snapshot_task = asyncio.create_task(_snapshot_loop(app))
    app.state.snapshot_task = snapshot_task

    logger.info("Background snapshot task started")

    yield

    # --- Shutdown ---
    logger.info("Shutting down FinAlly backend…")

    snapshot_task.cancel()
    try:
        await snapshot_task
    except asyncio.CancelledError:
        pass

    await source.stop()
    logger.info("Market data source stopped")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    application = FastAPI(
        title="FinAlly API",
        description="AI Trading Workstation — backend API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # --- SSE stream router (market data subsystem owns this) ---
    # create_stream_router needs the cache, but we don't have it yet at
    # module import time.  We mount it lazily using a startup hook instead by
    # passing a lambda that reads from app.state.
    #
    # To keep things simple we create the router after startup with a real
    # PriceCache reference; we use a lazy proxy approach via a dependency so
    # the route is registered immediately but reads from app.state at request
    # time.  The cleanest solution for the SSE router factory (which closes
    # over the cache at creation time) is to register it inside lifespan —
    # but FastAPI does not support adding routes post-startup.
    #
    # Alternative: pass a container object that is populated during startup.
    # We use a simpler approach: create a placeholder PriceCache now, then
    # replace it on app.state during startup.  The stream router closes over
    # app.state so requests always see the live cache.
    #
    # Actually the cleanest pattern: create_stream_router receives the Request
    # and reads from request.app.state inside the handler.  The existing
    # stream.py reads price_cache directly (closure), so we pass a thin
    # wrapper that delegates to app.state at call time.
    #
    # Simplest correct approach: create a real PriceCache here, mount the
    # router with it, then REPLACE the same object's internals on startup.
    # But PriceCache is not designed for that.
    #
    # Chosen approach: create a _LateBoundCache that delegates all calls to
    # app.state.price_cache.  This is the least invasive solution.

    late_cache = _LateBoundCache(application)
    stream_router = create_stream_router(late_cache)  # type: ignore[arg-type]
    application.include_router(stream_router)

    # --- API routers ---
    from app.api.health import router as health_router
    from app.api.portfolio import router as portfolio_router
    from app.api.watchlist import router as watchlist_router

    application.include_router(health_router)
    application.include_router(portfolio_router)
    application.include_router(watchlist_router)

    # --- Chat router (llm-engineer owns this; guarded import) ---
    try:
        from app.chat.router import router as chat_router  # type: ignore[import]

        application.include_router(chat_router)
        logger.info("Chat router registered")
    except ImportError:
        logger.warning(
            "app.chat.router not found — chat endpoint unavailable. "
            "This is expected during Wave 2 development."
        )

    # --- Static file serving (must be LAST so /api/* routes take precedence) ---
    _mount_static(application)

    return application


class _LateBoundCache:
    """Thin wrapper that delegates PriceCache method calls to app.state.price_cache.

    This lets create_stream_router() be called at module import time while the
    real PriceCache is only created during startup.
    """

    def __init__(self, app: FastAPI) -> None:
        self._app = app

    def _cache(self) -> PriceCache:
        return self._app.state.price_cache

    def get_all(self):  # noqa: ANN201
        return self._cache().get_all()

    def get(self, ticker: str):  # noqa: ANN201
        return self._cache().get(ticker)

    def get_price(self, ticker: str):  # noqa: ANN201
        return self._cache().get_price(ticker)

    def update(self, ticker: str, price: float, timestamp=None):  # noqa: ANN001, ANN201
        return self._cache().update(ticker, price, timestamp)

    def remove(self, ticker: str) -> None:
        self._cache().remove(ticker)

    @property
    def version(self) -> int:
        return self._cache().version

    def __len__(self) -> int:
        return len(self._cache())

    def __contains__(self, ticker: str) -> bool:
        return ticker in self._cache()


def _mount_static(application: FastAPI) -> None:
    """Mount the Next.js static export at '/' if the directory exists."""
    # In-container path (Dockerfile copies frontend build here)
    container_static = Path("/app/backend/static")
    # Local dev path (relative to project root, two levels up from this file)
    local_static = Path(__file__).resolve().parents[1] / "static"

    static_dir: Path | None = None
    if container_static.exists():
        static_dir = container_static
    elif local_static.exists():
        static_dir = local_static

    if static_dir is not None:
        application.mount(
            "/",
            StaticFiles(directory=str(static_dir), html=True),
            name="static",
        )
        logger.info("Static files mounted from %s", static_dir)
    else:
        logger.info(
            "Static directory not found (%s or %s) — skipping static file mount. "
            "Run the Next.js build or set up the static directory for full-stack serving.",
            container_static,
            local_static,
        )


# ---------------------------------------------------------------------------
# Application instance (referenced by uvicorn as app.main:app)
# ---------------------------------------------------------------------------

app = create_app()
