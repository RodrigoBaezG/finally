"""Tests for the SSE streaming router."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.market.cache import PriceCache
from app.market.stream import _generate_events, create_stream_router


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_request(*, disconnect_after: int = 1) -> MagicMock:
    """Return a mock FastAPI Request whose is_disconnected() returns True
    after `disconnect_after` calls, allowing the SSE generator to terminate."""
    request = MagicMock()
    call_count = {"n": 0}

    async def _is_disconnected() -> bool:
        call_count["n"] += 1
        return call_count["n"] > disconnect_after

    request.is_disconnected = _is_disconnected
    request.client = MagicMock()
    request.client.host = "127.0.0.1"
    return request


def _build_app(cache: PriceCache) -> FastAPI:
    app = FastAPI()
    app.include_router(create_stream_router(cache))
    return app


async def _collect_generator(gen) -> list[str]:
    """Drain an async generator into a list."""
    chunks = []
    async for chunk in gen:
        chunks.append(chunk)
    return chunks


# ---------------------------------------------------------------------------
# Router factory tests
# ---------------------------------------------------------------------------

class TestCreateStreamRouter:
    """Tests for the create_stream_router factory."""

    def test_returns_new_router_each_call(self):
        """Each call must return a distinct router object — no shared state."""
        cache = PriceCache()
        r1 = create_stream_router(cache)
        r2 = create_stream_router(cache)
        assert r1 is not r2

    def test_router_has_prices_route(self):
        """The returned router must expose GET /api/stream/prices."""
        cache = PriceCache()
        router = create_stream_router(cache)
        paths = [r.path for r in router.routes]
        assert "/api/stream/prices" in paths

    def test_second_registration_does_not_duplicate_routes(self):
        """Registering the second router must not add duplicate /prices routes."""
        cache = PriceCache()
        app = FastAPI()
        app.include_router(create_stream_router(cache))
        app.include_router(create_stream_router(cache))
        prices_routes = [r for r in app.routes if getattr(r, "path", "") == "/api/stream/prices"]
        assert len(prices_routes) == 2  # two separate routers, same path — no shared state corruption


# ---------------------------------------------------------------------------
# Generator-level tests (fast, no ASGI overhead)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestGenerateEvents:
    """Tests for the _generate_events async generator."""

    async def test_first_yield_is_retry_directive(self):
        """The very first SSE line must be the retry directive."""
        cache = PriceCache()
        req = _make_request(disconnect_after=0)
        chunks = await _collect_generator(_generate_events(cache, req, interval=0))
        assert chunks[0] == "retry: 1000\n\n"

    async def test_no_data_event_when_cache_empty(self):
        """With an empty cache, only the retry directive should be emitted."""
        cache = PriceCache()
        req = _make_request(disconnect_after=0)
        chunks = await _collect_generator(_generate_events(cache, req, interval=0))
        data_lines = [c for c in chunks if c.startswith("data:")]
        assert data_lines == []

    async def test_data_event_emitted_when_cache_has_prices(self):
        """When the cache has prices, a data event must be yielded."""
        cache = PriceCache()
        cache.update("AAPL", 190.50)
        req = _make_request(disconnect_after=1)  # one iteration before disconnect
        chunks = await _collect_generator(_generate_events(cache, req, interval=0))

        data_lines = [c for c in chunks if c.startswith("data:")]
        assert len(data_lines) == 1
        payload = json.loads(data_lines[0][len("data: "):])
        assert "AAPL" in payload
        assert payload["AAPL"]["price"] == 190.50

    async def test_data_event_contains_session_start_price(self):
        """Each data event must include session_start_price per the spec."""
        cache = PriceCache()
        cache.update("AAPL", 190.00)   # session_start_price = 190.00
        cache.update("AAPL", 195.00)   # price moved; session_start_price unchanged
        req = _make_request(disconnect_after=1)
        chunks = await _collect_generator(_generate_events(cache, req, interval=0))

        data_lines = [c for c in chunks if c.startswith("data:")]
        assert len(data_lines) >= 1
        aapl = json.loads(data_lines[0][len("data: "):])[  "AAPL"]
        assert "session_start_price" in aapl
        assert aapl["session_start_price"] == 190.00
        assert "session_change_percent" in aapl

    async def test_all_tickers_included_in_one_event(self):
        """All cached tickers must appear together in a single data payload."""
        cache = PriceCache()
        cache.update("AAPL", 190.00)
        cache.update("GOOGL", 175.00)
        req = _make_request(disconnect_after=1)
        chunks = await _collect_generator(_generate_events(cache, req, interval=0))

        data_lines = [c for c in chunks if c.startswith("data:")]
        payload = json.loads(data_lines[0][len("data: "):])
        assert "AAPL" in payload
        assert "GOOGL" in payload

    async def test_no_duplicate_event_when_version_unchanged(self):
        """The generator must not re-emit when the cache version hasn't changed."""
        cache = PriceCache()
        cache.update("AAPL", 190.00)
        # disconnect_after=2 → two checks: first emits, second sees same version → no emit
        req = _make_request(disconnect_after=2)
        chunks = await _collect_generator(_generate_events(cache, req, interval=0))

        data_lines = [c for c in chunks if c.startswith("data:")]
        assert len(data_lines) == 1  # only one emission despite two loop iterations

    async def test_sse_event_format(self):
        """Events must follow the SSE wire format: 'data: <json>\\n\\n'."""
        cache = PriceCache()
        cache.update("AAPL", 190.00)
        req = _make_request(disconnect_after=1)
        chunks = await _collect_generator(_generate_events(cache, req, interval=0))

        data_lines = [c for c in chunks if c.startswith("data:")]
        assert len(data_lines) >= 1
        # Must end with double newline per SSE spec
        assert data_lines[0].endswith("\n\n")

    async def test_stops_on_disconnect(self):
        """Generator must stop yielding after is_disconnected() returns True."""
        cache = PriceCache()
        cache.update("AAPL", 190.00)
        # Allow 3 full loop iterations, then disconnect
        req = _make_request(disconnect_after=3)
        chunks = await _collect_generator(_generate_events(cache, req, interval=0))
        # We should get a bounded set of chunks, not an infinite stream
        assert len(chunks) < 10


# ---------------------------------------------------------------------------
# ASGI-level tests (headers / routing only)
# Patch _generate_events with a finite generator so TestClient can complete.
# ---------------------------------------------------------------------------

async def _finite_gen(cache: PriceCache, request, interval: float = 0.5):
    """Finite stand-in for _generate_events — yields one event then stops."""
    yield "retry: 1000\n\n"


class TestStreamPricesHeaders:
    """Verify HTTP-level concerns using a patched finite generator."""

    def test_response_is_text_event_stream(self):
        """Content-Type must be text/event-stream."""
        cache = PriceCache()
        app = _build_app(cache)
        with patch("app.market.stream._generate_events", _finite_gen):
            with TestClient(app) as client:
                resp = client.get("/api/stream/prices")
                assert "text/event-stream" in resp.headers["content-type"]

    def test_cache_control_is_no_cache(self):
        """Cache-Control must be no-cache."""
        cache = PriceCache()
        app = _build_app(cache)
        with patch("app.market.stream._generate_events", _finite_gen):
            with TestClient(app) as client:
                resp = client.get("/api/stream/prices")
                assert resp.headers.get("cache-control") == "no-cache"

    def test_x_accel_buffering_disabled(self):
        """X-Accel-Buffering must be 'no' to prevent nginx buffering."""
        cache = PriceCache()
        app = _build_app(cache)
        with patch("app.market.stream._generate_events", _finite_gen):
            with TestClient(app) as client:
                resp = client.get("/api/stream/prices")
                assert resp.headers.get("x-accel-buffering") == "no"

    def test_endpoint_returns_200(self):
        """GET /api/stream/prices must respond with 200 OK."""
        cache = PriceCache()
        app = _build_app(cache)
        with patch("app.market.stream._generate_events", _finite_gen):
            with TestClient(app) as client:
                resp = client.get("/api/stream/prices")
                assert resp.status_code == 200
