/**
 * Scenario 2: Prices stream
 * Verifies that price values update within a few seconds of page load.
 * The simulator ticks every ~500ms so multiple updates should arrive in 5s.
 */
import { test, expect } from '@playwright/test';

test.describe('Price streaming (SSE)', () => {
  test('at least one ticker price updates within 5 seconds', async ({ page }) => {
    await page.goto('/');

    // Wait for the watchlist to load
    await expect(page.getByTestId('watchlist-row-AAPL')).toBeVisible({ timeout: 8000 });

    // Capture the initial price for AAPL
    const priceEl = page.getByTestId('watchlist-price-AAPL');
    await expect(priceEl).toBeVisible({ timeout: 5000 });

    const initialText = await priceEl.textContent();

    // Poll until the displayed price changes — the simulator ticks every ~500ms
    let changed = false;
    await expect.poll(
      async () => {
        const current = await priceEl.textContent();
        if (current !== initialText) {
          changed = true;
        }
        return changed;
      },
      { timeout: 8000, intervals: [500, 500, 500, 500, 500, 500, 500, 500, 500, 500, 500, 500, 500, 500, 500, 500] }
    ).toBe(true);
  });

  test('SSE /api/stream/prices endpoint streams batch events with ticker prices', async ({
    page,
  }) => {
    // The SSE stream sends one event per tick containing a dict keyed by ticker:
    //   { "AAPL": { ticker, price, ... }, "GOOGL": { ... }, ... }
    // We open an EventSource in the page context and collect at least 2 events.
    await page.goto('/');

    const eventData = await page.evaluate(
      () =>
        new Promise<string[]>((resolve) => {
          const events: string[] = [];
          const es = new EventSource('/api/stream/prices');
          es.onmessage = (e) => {
            events.push(e.data);
            if (events.length >= 2) {
              es.close();
              resolve(events);
            }
          };
          // Timeout fallback
          setTimeout(() => {
            es.close();
            resolve(events);
          }, 8000);
        })
    );

    expect(eventData.length).toBeGreaterThanOrEqual(2);

    // Each event is a JSON dict: { "TICKER": { ticker, price, ... }, ... }
    for (const raw of eventData) {
      const parsed = JSON.parse(raw);
      const tickerKeys = Object.keys(parsed);
      expect(tickerKeys.length).toBeGreaterThan(0);
      // Check the first ticker entry has the expected shape
      const firstEntry = parsed[tickerKeys[0]];
      expect(typeof firstEntry.ticker).toBe('string');
      expect(typeof firstEntry.price).toBe('number');
      expect(firstEntry.price).toBeGreaterThan(0);
    }
  });
});
