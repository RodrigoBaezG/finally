# FinAlly E2E Test Suite

Playwright tests for the FinAlly AI Trading Workstation. Tests run against a live app instance with `LLM_MOCK=true` for deterministic, free AI chat responses.

## Prerequisites

- Node.js 18+
- Python 3.12+ with `uv`
- The `frontend/out/` static export must exist

## Quick start (Path B — local run, fastest)

### 1. Build the frontend

```bash
cd frontend
npm install
npm run build        # produces frontend/out/
cd ..
mkdir -p backend/static
cp -R frontend/out/* backend/static/
```

### 2. Start the backend

```bash
cd backend
LLM_MOCK=true uv run uvicorn app.main:app --port 8000
```

Verify it started:

```bash
curl http://localhost:8000/api/health   # should return {"status":"ok"}
```

### 3. Install Playwright and run tests

```bash
cd test
npm install
npx playwright install chromium
npx playwright test
```

## Running against Docker (Path A — closer to production)

```bash
docker compose -f test/docker-compose.test.yml up -d finally-test
# Wait ~30s for the container to become healthy
curl http://localhost:8000/api/health

cd test
npm install
npx playwright install chromium
BASE_URL=http://localhost:8000 npx playwright test
```

## Environment variables

| Variable   | Default                  | Purpose                                  |
|------------|--------------------------|------------------------------------------|
| `BASE_URL` | `http://localhost:8000`  | App URL for Playwright tests             |

`LLM_MOCK=true` is set on the backend (not in this directory). Without it, the chat tests will call OpenRouter and require a real `OPENROUTER_API_KEY`.

## Test structure

```
test/
  e2e/
    initial-load.spec.ts   — Fresh start: health, default watchlist, cash, SSE connection
    prices-stream.spec.ts  — SSE price streaming: DOM mutation + raw EventSource check
    watchlist.spec.ts      — Watchlist CRUD: add, remove, unknown ticker error
    trade.spec.ts          — Buy/sell flows: positions appear/disappear, cash updates
    chat.spec.ts           — AI chat (mocked): buy via chat, watchlist remove via chat
    portfolio.spec.ts      — Heatmap visible, P&L chart canvas, positions table
  globalSetup.ts           — Restores default 10-ticker watchlist before suite runs
  playwright.config.ts     — Chromium only, 1 worker, screenshots+traces on failure
  package.json
  README.md
```

## LLM mock mode

When `LLM_MOCK=true`, the backend uses keyword matching instead of calling OpenRouter:

- `"buy N TICKER"` → executes a buy trade
- `"sell N TICKER"` → executes a sell trade
- `"add TICKER to watchlist"` → adds the ticker
- `"remove TICKER from watchlist"` → removes the ticker
- `"analyze portfolio"` / `"holdings"` etc. → returns a portfolio summary
- Anything else → default greeting

This makes all chat tests deterministic and free.

## Viewing results

After a test run:

```bash
npx playwright show-report   # opens the HTML report in your browser
```

Screenshots and traces for failures are in `test-results/`.
