# FinAlly — Comprehensive Project Review

**Reviewer:** Claude Sonnet 4.6
**Date:** 2026-04-14
**Scope:** Full codebase as of current main branch

---

## Executive Summary

The project is at an early stage. The only component that has been built and shipped is the market data subsystem (`backend/app/market/`). Everything else described in the plan — the FastAPI application shell, database layer, portfolio/trade API, LLM integration, frontend, Docker container, scripts, and E2E tests — does not yet exist. The review therefore covers the completed market data component in depth and then maps out every missing piece against the spec.

---

## 1. Backend — Market Data Subsystem

### 1.1 Code Quality: Strong

The market data subsystem is well-structured and cleanly written. The strategy pattern (`MarketDataSource` ABC, two concrete implementations) is the right design for this requirement. The `PriceCache` as a shared, single point-of-truth between producers and consumers is sound. The `create_stream_router` factory pattern correctly avoids module-level globals.

### 1.2 Bugs and Correctness Issues

**B1 — `PriceUpdate.to_dict()` is missing `session_start_price` (spec violation)**
The plan (section 6, SSE Streaming) states: "Each SSE event contains ticker, price, previous price, session-start price, timestamp, and change direction." The `PriceUpdate` model in `backend/app/market/models.py` has no `session_start_price` field, and `to_dict()` does not emit it. The plan also says "Records each ticker's seed price as its session-start price; all 'change since session start %' calculations use this baseline." Without this field, the frontend cannot display session-change percentage, which is explicitly called out in the watchlist panel spec. This must be added before any downstream consumer (frontend, portfolio) is built.

**B2 — Race condition in `SimulatorDataSource.add_ticker`**
In `backend/app/market/simulator.py`, `add_ticker` calls `self._sim.add_ticker(ticker)` (which modifies `self._sim._tickers`, `self._sim._prices`, and rebuilds the Cholesky matrix) while `_run_loop` is concurrently reading `self._sim._tickers` and calling `self._sim.step()` in a separate asyncio task. Because `GBMSimulator` methods are not thread-safe and the event loop runs tasks concurrently, there is a potential for interleaved execution between `step()` and the index rebuild inside `_rebuild_cholesky`. This is a correctness risk when `add_ticker` is called via a future watchlist API endpoint while the loop is running. Mitigation: protect `GBMSimulator` mutations with an `asyncio.Lock`.

**B3 — `timestamp=0` accepted silently in `PriceCache.update`**
The method signature is `timestamp: float | None = None` and uses `ts = timestamp or time.time()`. The `or` idiom treats `0` as falsy, so passing an explicit `timestamp=0` would silently be replaced by the current time. This is unlikely in practice but misleading. The guard should be `ts = timestamp if timestamp is not None else time.time()`.

**B4 — `MassiveDataSource` does not normalise ticker case on `start()`**
`add_ticker` and `remove_ticker` both call `.upper().strip()`, but `start(tickers)` does `self._tickers = list(tickers)` with no normalisation. If the caller passes lowercase tickers at start-up they will be stored as-is. Inconsistency with subsequent `add_ticker`/`remove_ticker` calls could cause duplicates.

**B5 — SSE version-check optimisation can suppress the first event**
In `backend/app/market/stream.py`, `last_version` is initialised to `-1`. If the cache is pre-seeded synchronously before the first SSE client connects, `current_version` will already be greater than `-1` and the first event will fire correctly. However if the cache is empty at connect time (`current_version == 0`, which equals `last_version + 1 = 0` only after one update), the logic is still sound. This is not a bug but worth a comment so future maintainers understand why `-1` is correct.

### 1.3 Security Issues

**S1 — Live API key committed to `.env` in the repository**
`/c/Users/Kbaez/Desktop/Proyectos/finally/.env` contains a real `OPENROUTER_API_KEY` beginning with `sk-or-v1-`. This file is committed to the git repository (it appears in the project root alongside committed files, and no `.gitignore` is present in the repository listing). API keys must never be committed. The key should be rotated immediately, `.env` must be added to `.gitignore`, and `.env.example` with placeholder values should be committed instead. The README already references `.env.example` as the setup step, so the intent was correct — the file just was not actually gitignored.

**S2 — `SESSION_SECRET_KEY` also in committed `.env`**
The same `.env` contains `SESSION_SECRET_KEY=kanban-mvp-secret-change-before-production-eX7mPqR9wZn2`. The comment in the value ("change before production") signals this was a known placeholder, but it is still exposed in version control.

**S3 — No input validation on ticker symbols**
`MassiveDataSource.add_ticker` normalises case and strips whitespace but does not validate that the input is a plausible ticker (e.g., alphanumeric, length 1–5). The future watchlist `POST /api/watchlist` endpoint will accept user-supplied tickers and pass them through to this method. Without validation, a user could inject malformed strings that propagate into the Polygon.io API request or into the cache keyed by an arbitrary string.

### 1.4 Missing Features vs Spec (Market Data Layer Only)

**M1 — No `session_start_price` tracking**
As noted in B1. The cache stores only the latest price and derives `previous_price` from the prior update. A separate field is needed to record the price at session start (i.e., the seed/first-tick price). This is distinct from `previous_price` (tick-to-tick) and is required for the "change since session start %" display in the watchlist panel.

**M2 — SSE stream does not consult the live watchlist from the database**
The plan states: "On each tick (~500ms), the backend re-reads the current watchlist and streams prices for all tickers currently in it — newly added tickers appear in the next tick automatically, no client reconnect required." The current `_generate_events` in `stream.py` streams whatever is in `price_cache.get_all()`, which is correct at the cache level. However, the SSE router has no dependency on the database watchlist — this coupling will need to be wired up when the watchlist API is built so that `source.add_ticker` / `source.remove_ticker` stay in sync.

### 1.5 Code Quality Observations

- The `GBMSimulator` math is correct and well-commented. The `DEFAULT_DT` derivation from trading seconds is precise and instructive.
- Correlation matrix construction is quadratic (`O(n^2)`) but since `n < 50` this is fine.
- The exception swallowing in `SimulatorDataSource._run_loop` (`logger.exception` + continue) is appropriate for a background task — a crash should not kill the whole app.
- `massive_client.py` correctly uses `asyncio.to_thread` for the synchronous Massive SDK call.
- The `__all__` in `backend/app/market/__init__.py` is properly defined but does not export `SimulatorDataSource` or `MassiveDataSource`. This is fine since downstream code should use the factory, not construct sources directly.

### 1.6 Test Suite

The test suite is thorough for what has been built. 73 tests across 6 modules is solid coverage. Specific observations:

- `test_simulator.py` line 128–131: the decimal-place check using string parsing is fragile. `round(result["AAPL"], 2) == result["AAPL"]` would be more robust.
- `test_massive.py` tests do not cover the `start()` path's ticker normalisation gap (B4 above).
- There are no tests for `stream.py` — the SSE generator is untested. An async generator test using `AsyncGenerator` iteration would cover the core event emission logic.
- `conftest.py` defines `event_loop_policy` but this fixture is never used in the test files (they rely on `pytest-asyncio`'s auto mode). It is harmless but dead code.
- The `test_models.py` line 69 hardcodes the expected `change_percent` as `0.2632` with a comment showing the calculation. This is correct but the precision comes from `round(..., 4)` — a note tying the assertion to the implementation's rounding would prevent future confusion.

---

## 2. Backend — What Is Not Yet Built

The following components are required by the spec and do not exist:

### 2.1 FastAPI Application Entry Point
No `main.py`, `app.py`, or equivalent exists. There is no FastAPI application object, no lifespan handler (for starting/stopping the market data source), no static file serving, and no health check endpoint. The `create_stream_router` factory exists and works in isolation but is not wired into any app.

**Required:**
- `backend/app/main.py` with a FastAPI app, lifespan context manager calling `source.start()` / `source.stop()`, static file mount for the Next.js export, and inclusion of all routers.
- `GET /api/health` endpoint.

### 2.2 Database Layer
No SQLite initialisation, schema, or seeding exists. The plan (section 7) defines six tables: `users_profile`, `watchlist`, `positions`, `trades`, `portfolio_snapshots`, `chat_messages`. None of these are implemented.

**Required:**
- `backend/app/db/` directory with `schema.sql` (or inline DDL), a `database.py` module providing a connection factory, and a `seed.py` / `init.py` for lazy initialisation on startup.

### 2.3 Portfolio API
No portfolio endpoints exist. Required per spec:
- `GET /api/portfolio` — positions, cash, total value, unrealized P&L
- `POST /api/portfolio/trade` — execute buy/sell market order
- `GET /api/portfolio/history` — portfolio value snapshots

Trade execution logic (average cost calculation on buys, partial/full sell handling, cash updates, position deletion when quantity reaches zero) is entirely unimplemented.

### 2.4 Watchlist API
No watchlist endpoints exist. Required per spec:
- `GET /api/watchlist` — current tickers with latest prices from cache
- `POST /api/watchlist` — add ticker (validate against price source; return 400 if unknown)
- `DELETE /api/watchlist/{ticker}` — remove ticker

The `POST` validation step ("validates ticker is known to the price source") is non-trivial — it requires the Massive API or simulator to confirm the ticker exists before persisting it.

### 2.5 Chat / LLM Integration
No chat endpoint or LLM integration exists. Required per spec:
- `POST /api/chat`
- LiteLLM → OpenRouter wiring
- Structured output schema (`message`, `trades`, `watchlist_changes`)
- Auto-execution of trades and watchlist changes from LLM response
- `LLM_MOCK=true` mode for testing
- System prompt construction with portfolio context

### 2.6 Portfolio Snapshot Background Task
A background task must record portfolio value snapshots every 30 seconds (and immediately after each trade) into the `portfolio_snapshots` table. This is not implemented.

---

## 3. Frontend

No frontend code exists at all. The `frontend/` directory is absent. Required per spec:

- Next.js project with TypeScript, Tailwind CSS, static export (`output: 'export'`)
- All UI panels: watchlist, main chart, portfolio heatmap (treemap), P&L chart, positions table, trade bar, AI chat panel, header
- `EventSource` SSE connection to `/api/stream/prices`
- Price flash animations (CSS transition, ~500ms)
- Sparkline mini-charts accumulated from SSE since page load
- Canvas-based charting library (Lightweight Charts or Recharts)
- Connection status indicator (two states: green dot / red dot)
- Live portfolio value computed client-side from SSE prices

---

## 4. Docker and Deployment

No `Dockerfile`, `docker-compose.yml`, `scripts/`, or `test/` directory exists. Required per spec:

- Multi-stage `Dockerfile` (Node 20 → Python 3.12/uv)
- `docker-compose.yml` convenience wrapper
- `scripts/start_mac.sh`, `scripts/stop_mac.sh`, `scripts/start_windows.ps1`, `scripts/stop_windows.ps1`
- `db/.gitkeep` (volume mount target; `finally.db` gitignored)
- `.env.example` with placeholder values
- `.gitignore` that covers `.env`, `db/finally.db`, `__pycache__`, `.next`, `node_modules`

The README documents a `docker build -t finally .` command and references `scripts/start_*.sh` — both of which will fail because these files do not exist.

---

## 5. E2E Tests

No `test/` directory, no Playwright tests, and no `docker-compose.test.yml` exist. Required per spec:

- `test/docker-compose.test.yml` spinning up the app container and a Playwright container
- Playwright test scenarios: fresh start, add/remove ticker, buy/sell shares, heatmap renders, AI chat (mocked), SSE resilience

---

## 6. Overall Architecture Assessment

### What the spec gets right and is correctly reflected in the code

- Strategy pattern for market data is a good call and is properly implemented
- PriceCache thread-safety with `threading.Lock` is correct (asyncio and sync code can both write safely in the same process)
- `asyncio.to_thread` for the synchronous Massive SDK is the right approach
- Version-based SSE change detection avoids unnecessary event emission
- The plan's decision to use SSE over WebSockets is appropriate for this data flow

### Architectural concerns for the next phase

**A1 — No dotenv loading in the backend**
The plan says "The backend reads `.env` from the project root." The `factory.py` uses `os.environ.get("MASSIVE_API_KEY")` directly. There is no `python-dotenv` or equivalent in `pyproject.toml` dependencies. When running outside Docker (e.g., during development with `uvicorn`), the `.env` file will not be loaded automatically. Either add `python-dotenv` to dependencies and call `load_dotenv()` at startup, or document that developers must `export` variables manually. Note: `python-dotenv` is not listed in `pyproject.toml`.

**A2 — No `litellm` or `httpx` in dependencies**
The LLM integration requires `litellm` (per the plan) and likely `httpx` for async HTTP. Neither is in `pyproject.toml`. They must be added before the chat endpoint is built.

**A3 — Single `Lock` for PriceCache, async context**
`PriceCache` uses `threading.Lock`. Since FastAPI runs on an asyncio event loop, holding a threading lock inside an `async` function will block the event loop. Currently the SSE generator calls `price_cache.get_all()` which acquires the lock briefly — this is safe because the lock is not held across an `await`. Maintainers must ensure this constraint is never violated as the codebase grows. An `asyncio.Lock` would be safer for async consumers. The current threading lock is appropriate if the Massive client (which runs in a thread) is the only async-blocking writer.

**A4 — Watchlist source-of-truth ambiguity**
The plan has two sources of truth for the watchlist: the SQLite `watchlist` table and the in-memory `MarketDataSource` ticker list. When the app restarts, the `MarketDataSource` must be seeded from the database, not from `seed_prices.py`'s hardcoded list. The `seed_prices.py` default tickers and the database seed data must be kept in sync. Currently `simulator.py` is entirely decoupled from the database — the startup sequence will need to read the `watchlist` table first, then call `source.start(tickers_from_db)`.

**A5 — No graceful shutdown of the SSE generator on application shutdown**
When the FastAPI app shuts down (SIGTERM inside Docker), in-flight SSE connections will be cancelled. The `_generate_events` generator handles `asyncio.CancelledError` via a `try/except` which logs and exits — this is correct. However if the Uvicorn worker exits before the background market data task is stopped, the background task may log errors. The lifespan handler (A1 above) must call `source.stop()` in the shutdown phase.

---

## 7. Priority Action List

In order of urgency:

2. **Add `session_start_price` to `PriceUpdate` and `PriceCache`** — required by spec and by the frontend before it can be built.
3. **Build the FastAPI application entry point** — nothing else can be integrated without it.
4. **Implement the database layer** — all API endpoints depend on it.
5. **Implement portfolio and watchlist APIs** — core application functionality.
6. **Add `python-dotenv` and `litellm` to `pyproject.toml`** — unblock LLM integration.
7. **Implement the LLM chat endpoint**.
8. **Build the frontend**.
9. **Write the Dockerfile and scripts**.
10. **Write E2E tests**.
11. **Fix the minor correctness issues** (B2 asyncio lock, B3 timestamp guard, B4 normalisation on start) — low risk now but higher risk once concurrent API requests begin.

---

## 8. Files Reviewed

- `backend/app/market/__init__.py`
- `backend/app/market/interface.py`
- `backend/app/market/models.py`
- `backend/app/market/cache.py`
- `backend/app/market/simulator.py`
- `backend/app/market/massive_client.py`
- `backend/app/market/factory.py`
- `backend/app/market/stream.py`
- `backend/app/market/seed_prices.py`
- `backend/market_data_demo.py`
- `backend/pyproject.toml`
- `backend/CLAUDE.md`
- `backend/tests/conftest.py`
- `backend/tests/market/test_models.py`
- `backend/tests/market/test_cache.py`
- `backend/tests/market/test_simulator.py`
- `backend/tests/market/test_simulator_source.py`
- `backend/tests/market/test_factory.py`
- `backend/tests/market/test_massive.py`
- `planning/PLAN.md`
- `planning/MARKET_DATA_SUMMARY.md`
- `CLAUDE.md`
- `README.md`
- `.env`
