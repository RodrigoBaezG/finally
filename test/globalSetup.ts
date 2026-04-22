/**
 * Global setup: runs once before all Playwright tests.
 *
 * Restores the default watchlist (10 tickers) so that the "fresh start"
 * assertions are valid regardless of what previous test runs left behind.
 * Positions and cash are NOT reset here — tests that depend on specific
 * portfolio state manage that themselves in beforeEach.
 */
import { request as playwrightRequest } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'http://localhost:8000';

const DEFAULT_TICKERS = ['AAPL', 'GOOGL', 'MSFT', 'AMZN', 'TSLA', 'NVDA', 'META', 'JPM', 'V', 'NFLX'];

export default async function globalSetup() {
  const ctx = await playwrightRequest.newContext({ baseURL: BASE_URL });

  // Fetch current watchlist
  const wlRes = await ctx.get('/api/watchlist');
  const current: Array<{ ticker: string }> = await wlRes.json();
  const currentTickers = new Set(current.map((item) => item.ticker));

  // Add any missing default tickers
  for (const ticker of DEFAULT_TICKERS) {
    if (!currentTickers.has(ticker)) {
      await ctx.post('/api/watchlist', { data: { ticker } });
    }
  }

  await ctx.dispose();
}
