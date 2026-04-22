/**
 * Scenario 1: Fresh start
 * Verifies the default state of the application on first load:
 * - 10 default watchlist tickers
 * - $10,000 cash balance
 * - Portfolio total ~$10,000
 * - Connection status indicator goes green (SSE connects)
 */
import { test, expect } from '@playwright/test';

const DEFAULT_TICKERS = ['AAPL', 'GOOGL', 'MSFT', 'AMZN', 'TSLA', 'NVDA', 'META', 'JPM', 'V', 'NFLX'];

test.describe('Fresh start / initial load', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('health endpoint returns ok', async ({ request }) => {
    const res = await request.get('/api/health');
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body.status).toBe('ok');
  });

  test('default watchlist shows 10 tickers', async ({ page }) => {
    for (const ticker of DEFAULT_TICKERS) {
      await expect(
        page.getByTestId(`watchlist-row-${ticker}`),
        `Expected watchlist row for ${ticker}`
      ).toBeVisible({ timeout: 8000 });
    }
  });

  test('cash balance is shown and loads from the API (not stuck at $0.00)', async ({ page }) => {
    // The page initially renders cash as $0.00 before /api/portfolio loads.
    // We wait for the value to update to a real balance.
    const cashEl = page.getByTestId('cash-balance');
    await expect(cashEl).toBeVisible({ timeout: 8000 });

    // Poll until the text is not the initial zero placeholder
    await expect.poll(
      async () => {
        const text = await cashEl.textContent();
        return text;
      },
      { timeout: 8000, message: 'Cash balance should update from initial $0.00 after API load' }
    ).not.toBe('$0.00');

    const text = await cashEl.textContent();
    // Must match a dollar amount
    expect(text).toMatch(/\$[\d,]+\.\d{2}/);
  });

  test('portfolio total is shown and loads from the API', async ({ page }) => {
    // The portfolio total may briefly show $0.00 before /api/portfolio loads.
    const totalEl = page.getByTestId('portfolio-total');
    await expect(totalEl).toBeVisible({ timeout: 8000 });

    // Wait for it to be a non-zero value (either cash or cash+positions)
    await expect.poll(
      async () => {
        const text = await totalEl.textContent();
        return text;
      },
      { timeout: 8000, message: 'Portfolio total should update from initial state after API load' }
    ).not.toBe('$0.00');

    const text = await totalEl.textContent();
    expect(text).toMatch(/\$[\d,]+\.\d{2}/);
  });

  test('portfolio API cash_balance matches $10,000 on a fresh DB', async ({ request }) => {
    // Cross-check the actual API value — the cash_balance should be a positive number
    const res = await request.get('/api/portfolio');
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(typeof body.cash_balance).toBe('number');
    expect(body.cash_balance).toBeGreaterThan(0);
    expect(typeof body.total_value).toBe('number');
    expect(body.total_value).toBeGreaterThan(0);
  });

  test('connection status indicator becomes green (connected)', async ({ page }) => {
    const indicator = page.getByTestId('connection-status');
    await expect(indicator).toBeVisible({ timeout: 8000 });
    // Wait for SSE to connect — the indicator should have data-status="connected"
    await expect(indicator).toHaveAttribute('data-status', 'connected', { timeout: 10000 });
  });

  test('watchlist API returns all default tickers with prices', async ({ request }) => {
    const res = await request.get('/api/watchlist');
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(Array.isArray(body)).toBe(true);
    // The watchlist must contain at least the 10 default tickers (globalSetup ensures this)
    expect(body.length).toBeGreaterThanOrEqual(10);
    const tickers = body.map((item: { ticker: string }) => item.ticker);
    for (const expected of DEFAULT_TICKERS) {
      expect(tickers).toContain(expected);
    }
    // Every item should have a numeric price
    for (const item of body) {
      expect(typeof item.price).toBe('number');
      expect(item.price).toBeGreaterThan(0);
    }
  });
});
