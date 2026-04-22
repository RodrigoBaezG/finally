# E2E Test Reports

Filed by **integration-tester** when a Playwright scenario fails. Each report names exactly one owner. Owners resolve the issue, re-run the suite, and mark the report resolved.

## Format

```
## [YYYY-MM-DD] Failure: <scenario name>
- Owner: frontend-engineer | backend-api-engineer | database-engineer | llm-engineer | devops-engineer
- Symptom: <what the test saw, 1–2 lines>
- Evidence: <console logs, failed network call, screenshot path, trace snippet>
- Expected: <what PLAN.md / the scenario requires>
- Repro: <minimal steps, exact test name>
- Status: open | in-progress | resolved
```

## Reports

<!-- Append new reports below this line -->

## [2026-04-21] Failure: Watchlist CRUD — UI does not update after removing a ticker

- Owner: frontend-engineer
- Symptom: Clicking the remove (×) button for a watchlist ticker sends DELETE /api/watchlist/{ticker} and gets a 204 No Content response, but the ticker row remains visible in the UI indefinitely. The `onWatchlistChange` callback is never invoked so `loadWatchlist()` never re-fetches.
- Evidence: `apiFetch<void>` in `frontend/src/lib/api.ts` unconditionally calls `res.json()` on every response. A 204 No Content response has no body, so `res.json()` throws a `SyntaxError`. The `catch {}` block in `WatchlistPanel.handleRemove` silently swallows this error and skips the `onWatchlistChange()` call. The DELETE does succeed server-side (verified via direct API call in the test), but the React state is never updated. Screenshot: `test/test-results/watchlist-Watchlist-CRUD-remove-a-ticker-from-the-watchlist-chromium/test-failed-1.png`
- Expected: Per PLAN.md §2, clicking the remove button should cause the ticker row to disappear immediately. The `onWatchlistChange` callback must fire after a successful removal so the watchlist state re-fetches.
- Repro: `npx playwright test e2e/watchlist.spec.ts --grep "remove a ticker from the watchlist"` (the original test before it was scoped to API-only). Alternatively: open the app, click × on any watchlist ticker — the row stays but the DB entry is deleted.
- Status: resolved
  - Fix [2026-04-22]: `apiFetch` now returns `undefined` when the response is 204 or has `content-length: 0` instead of calling `res.json()`. See `frontend/src/lib/api.ts`. Watchlist remove E2E test re-extended to assert the UI row disappears; full suite 29/29 green after fix + frontend rebuild.
