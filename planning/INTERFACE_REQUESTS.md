# Interface Requests

Cross-agent coordination log. When one engineer needs something from another (a new endpoint, a DB helper, a schema change, a static-file mount tweak, a stable selector, etc.), append a request here instead of editing outside your scope.

## Format

```
## [YYYY-MM-DD] <short title>
- Requester: <agent name>
- Owner: <agent name>
- Need: <what you need, 1–3 lines>
- Why: <which task/scenario depends on it>
- Proposed shape: <if you have one — function signature, endpoint path+payload, schema diff>
- Status: open | in-progress | resolved
```

## Requests

<!-- Append new requests below this line -->

## [2026-04-21] Backend API endpoint shapes — frontend assumptions
- Requester: frontend-engineer
- Owner: backend-api-engineer
- Need: Frontend was built against the shapes in PLAN.md §8-9. The following assumptions need confirmation:
  1. `GET /api/portfolio` returns `{cash_balance, total_value, positions: [{ticker, quantity, avg_cost, current_price, unrealized_pnl, pnl_percent}], total_unrealized_pnl}`.
  2. `POST /api/portfolio/trade` body `{ticker, quantity, side}` returns `{success, message, trade?: {ticker, side, quantity, price, executed_at}, portfolio?}`.
  3. `GET /api/portfolio/history` returns array of `{recorded_at: ISO string, total_value}`.
  4. `GET /api/watchlist` returns array of `{ticker, price, previous_price, session_start_price, session_change_percent, direction}`.
  5. `POST /api/chat` body `{message}` returns `{message, trades: [{ticker, side, quantity, price, status, error}], watchlist_changes: [{ticker, action, status, error}]}`. Arrays are always present (may be empty). `status` is `"executed"` or `"failed"`; `error` is `null` on success. See `backend/app/chat/router.py` response model.
  6. SSE `/api/stream/prices` sends a JSON dict keyed by ticker with each value matching `PriceUpdate.to_dict()` (confirmed from market module — ticker, price, previous_price, session_start_price, timestamp, change, change_percent, session_change_percent, direction).
- Why: Frontend renders against these shapes. Mismatch = broken UI at runtime.
- Proposed shape: As described above, derived from PLAN.md.
- Status: resolved
  - All shapes confirmed and implemented in `backend/app/api/portfolio.py`, `watchlist.py`, `schemas.py`.
  - `POST /api/portfolio/trade` errors use `HTTPException(400, detail=...)` so the frontend reads `.detail` on 400 responses.
  - `POST /api/chat` shape is the llm-engineer's scope; not implemented here.

## [2026-04-21] Static file mount path + uvicorn module path
- Requester: devops-engineer
- Owner: backend-api-engineer
- Need: Two contracts the Dockerfile bakes in:
  1. The uvicorn CMD uses `app.main:app` (run from `WORKDIR /app/backend`).
     Please confirm `app/main.py` contains the FastAPI instance named `app`.
  2. The Dockerfile copies the Next.js static export to `/app/backend/static/`.
     FastAPI must serve that directory at `/`. Expected:
     `app.mount("/", StaticFiles(directory="static", html=True), name="static")`
     registered **after** all `/api/*` routes so API routes take precedence.
- Why: Wrong path = 404 on frontend or all API routes at runtime.
- Proposed shape: No code change needed if the above matches your implementation.
  If the paths differ, update this request with the correct paths so the Dockerfile can be adjusted.
- Status: resolved
  - `backend/app/main.py` exports `app = create_app()` — `app.main:app` works from `WORKDIR /app/backend`.
  - Static mount checks `/app/backend/static/` first (container path), then `backend/static/` (local dev), skips gracefully if neither exists. Mount is registered last so all `/api/*` routes take precedence.
