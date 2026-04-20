# Review of `planning/PLAN.md`

**Reviewer:** Codex
**Date:** 2026-04-20
**Scope:** Planning document review only

## Findings

### 1. API contracts are underspecified for a multi-agent build
Severity: High

The plan lists endpoint names and broad responsibilities, but it does not define concrete request/response shapes for the endpoints agents will need to integrate against, especially `GET /api/portfolio`, `GET /api/watchlist`, `GET /api/portfolio/history`, and `POST /api/chat` ([PLAN.md](/C:/Users/Kbaez/Desktop/Proyectos/finally/planning/PLAN.md:251)). In a project explicitly built by multiple agents, that is a coordination risk: frontend, backend, and test work can all diverge while still "following the plan."

What is missing:
- Response examples with exact field names and types
- Error response shape and status code policy
- Whether numeric money values are rounded server-side or client-side
- Whether timestamps are ISO 8601 UTC strings everywhere
- Whether chat responses include partial failures for mixed-success action batches

Recommendation:
- Add a short contract section per endpoint with one success example and one failure example.
- Define a single shared error envelope, for example `{ "error": { "code": "...", "message": "..." } }`.
- Lock down numeric and timestamp conventions now.

### 2. Startup and initialization behavior is ambiguous
Severity: High

The plan says the database is initialized "on startup (or first request)" ([PLAN.md](/C:/Users/Kbaez/Desktop/Proyectos/finally/planning/PLAN.md:190)) and also says the price cache is pre-seeded at backend startup ([PLAN.md](/C:/Users/Kbaez/Desktop/Proyectos/finally/planning/PLAN.md:172)). Those statements leave open an important sequencing question: what is the authoritative startup order for loading the watchlist, initializing the market-data source, and pre-populating the cache?

Why this matters:
- If initialization happens lazily on first request, concurrent first requests can race.
- If the market data source starts before the database seed is loaded, default watchlist and cache state can drift.
- E2E tests become flaky if "first load" behavior depends on which endpoint is hit first.

Recommendation:
- Choose one startup model and state it explicitly. Prefer: app startup initializes schema, seeds default data if needed, loads watchlist from DB, starts market data, then serves requests.
- Reserve "lazy initialization" only for internal idempotent helpers if you really need it, but not as the primary contract.

### 3. Watchlist ownership is not defined clearly enough
Severity: High

The plan says the Massive poller tracks the union of watched tickers ([PLAN.md](/C:/Users/Kbaez/Desktop/Proyectos/finally/planning/PLAN.md:163)), and the SSE stream re-reads the current watchlist on each tick ([PLAN.md](/C:/Users/Kbaez/Desktop/Proyectos/finally/planning/PLAN.md:180)). It does not define which component is the source of truth or how add/remove operations propagate across DB, price source, cache, and connected clients.

Without that, several edge cases are unclear:
- When a ticker is removed from the watchlist, is it immediately removed from the poll set?
- If the chat agent adds a ticker and the validation succeeds but market data is delayed, what does `GET /api/watchlist` return in the meantime?
- Can the cache contain prices for tickers no longer in the watchlist?

Recommendation:
- State the source of truth explicitly: the DB watchlist should be authoritative.
- Define the write path: validate ticker -> persist DB change -> update market-data subscription set -> expose via API/SSE.
- Define read behavior for newly added tickers before first live update, since the plan already expects valid prices immediately.

### 4. LLM failure and degraded-mode behavior is missing
Severity: Medium

The first-launch UX says the AI chat panel is immediately ready ([PLAN.md](/C:/Users/Kbaez/Desktop/Proyectos/finally/planning/PLAN.md:20)), but the environment section makes `OPENROUTER_API_KEY` required ([PLAN.md](/C:/Users/Kbaez/Desktop/Proyectos/finally/planning/PLAN.md:124)). The plan does not say what happens when the key is missing, invalid, rate-limited, or OpenRouter is unavailable.

Recommendation:
- Define degraded behavior explicitly. Example: app still boots fully; chat UI is visible but disabled with a clear status message.
- Specify timeout, retry, and fallback rules for chat requests.
- Clarify whether failed LLM calls are persisted in `chat_messages`.

### 5. Trading and accounting rules need a few more constraints
Severity: Medium

The trading model is intentionally simple, but some core rules are still implicit rather than specified in the plan ([PLAN.md](/C:/Users/Kbaez/Desktop/Proyectos/finally/planning/PLAN.md:212), [PLAN.md](/C:/Users/Kbaez/Desktop/Proyectos/finally/planning/PLAN.md:262)).

Open items:
- Minimum trade quantity and decimal precision for fractional shares
- Whether zero or negative quantities are rejected at validation or schema layer
- Rounding policy for cash balance, average cost, and unrealized P&L
- Whether portfolio snapshots are best-effort or transactionally tied to trades

Recommendation:
- Add a short "Trading Rules" section with validation and rounding rules.
- Strongly prefer storing monetary calculations in integer cents or `Decimal`, even in SQLite-backed code, to avoid visible float drift.

### 6. The testing section names scenarios but not acceptance criteria
Severity: Medium

The testing strategy is directionally good, but several E2E scenarios are still too broad to act as a contract ([PLAN.md](/C:/Users/Kbaez/Desktop/Proyectos/finally/planning/PLAN.md:452)).

For example:
- "prices are streaming" should say what counts as proof
- "portfolio updates" should identify which UI elements must change
- "SSE resilience" should define expected reconnect timing and UI state

Recommendation:
- Add a lightweight acceptance checklist for each critical E2E flow.
- Include at least one deterministic path for chat actions under `LLM_MOCK=true`.

## Open Questions

1. Is the app allowed to run without a valid LLM key, or is chat considered mandatory for a successful launch?
2. Should `GET /api/watchlist` return only current prices, or also derived fields such as session change percent and sparkline seed/history metadata?
3. Is watchlist ticker validation expected to work identically in simulator mode and Massive mode?
4. Should chat-triggered trades execute atomically as a batch, or one-by-one with partial success reporting?

## Summary

The plan is strong on product vision and major architecture choices. The biggest weakness is contract precision: agents can agree on the high-level shape of the system while still building incompatible APIs and edge-case behavior. Tightening endpoint schemas, startup order, watchlist ownership, and degraded-mode rules would make this a much safer implementation contract.
