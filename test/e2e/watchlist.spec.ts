/**
 * Scenarios: Watchlist CRUD
 * - Remove a ticker (it disappears)
 * - Add a removed ticker back (validates and appears)
 * - Adding an unknown ticker returns a user-visible error
 *
 * Note: All seed prices are for the 10 default tickers only (AAPL, GOOGL, MSFT,
 * AMZN, TSLA, NVDA, META, JPM, V, NFLX). To test "add", we first remove one
 * ticker, then re-add it. The backend rejects any ticker not in SEED_PRICES.
 */
import { test, expect } from '@playwright/test';

test.describe('Watchlist CRUD', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    // Wait for watchlist to render before each test
    await expect(page.getByTestId('watchlist-row-AAPL')).toBeVisible({ timeout: 8000 });
  });

  test('remove a ticker: API DELETE succeeds and returns 204', async ({ page, request }) => {
    // Ensure NFLX is in the watchlist before we start
    await request.post('/api/watchlist', { data: { ticker: 'NFLX' } });
    await page.reload();
    await expect(page.getByTestId('watchlist-row-AAPL')).toBeVisible({ timeout: 8000 });
    await expect(page.getByTestId('watchlist-row-NFLX')).toBeVisible({ timeout: 5000 });

    const removeBtn = page.getByTestId('remove-ticker-btn-NFLX');
    await expect(removeBtn).toBeVisible({ timeout: 5000 });

    // Click remove and capture the DELETE network request
    const [deleteResponse] = await Promise.all([
      page.waitForResponse(
        (resp) =>
          resp.url().includes('/api/watchlist/NFLX') && resp.request().method() === 'DELETE',
        { timeout: 10000 }
      ),
      removeBtn.click(),
    ]);

    // The DELETE API call must succeed with 204 No Content
    expect(deleteResponse.status()).toBe(204);

    // Confirm via direct API that NFLX is removed from the backend
    const res = await request.get('/api/watchlist');
    const body = await res.json();
    const tickers = body.map((item: { ticker: string }) => item.ticker);
    expect(tickers).not.toContain('NFLX');

    // UI row should disappear after the client refetches the watchlist
    await expect(page.getByTestId('watchlist-row-NFLX')).not.toBeVisible({ timeout: 5000 });

    // Cleanup: re-add NFLX so DB is consistent for subsequent tests
    await request.post('/api/watchlist', { data: { ticker: 'NFLX' } });
  });

  test('add a ticker back after removing it', async ({ page, request }) => {
    // First remove V via API so we have a ticker to add
    await request.delete('/api/watchlist/V');

    // Reload so the UI reflects the removal
    await page.reload();
    await expect(page.getByTestId('watchlist-row-AAPL')).toBeVisible({ timeout: 8000 });
    await expect(page.getByTestId('watchlist-row-V')).not.toBeVisible({ timeout: 5000 });

    // Now add V back via the UI
    const addInput = page.getByTestId('add-ticker-input');
    const addBtn = page.getByTestId('add-ticker-btn');
    await addInput.fill('V');
    await addBtn.click();

    // V should re-appear in the watchlist
    await expect(page.getByTestId('watchlist-row-V')).toBeVisible({ timeout: 8000 });

    // Confirm via API
    const res = await request.get('/api/watchlist');
    const body = await res.json();
    const tickers = body.map((item: { ticker: string }) => item.ticker);
    expect(tickers).toContain('V');
  });

  test('adding an unknown ticker shows a user-visible error', async ({ page }) => {
    const addInput = page.getByTestId('add-ticker-input');
    const addBtn = page.getByTestId('add-ticker-btn');

    await addInput.fill('FAKEXYZ');
    await addBtn.click();

    // An error message should appear on the page
    // The WatchlistPanel renders addError in a div with class text-price-down
    const errorEl = page.locator('.text-price-down').first();
    await expect(errorEl).toBeVisible({ timeout: 8000 });
    const errorText = await errorEl.textContent();
    expect(errorText).toBeTruthy();
    expect(errorText!.length).toBeGreaterThan(0);

    // The fake ticker should NOT appear in the watchlist
    await expect(page.getByTestId('watchlist-row-FAKEXYZ')).not.toBeVisible();
  });

  test('watchlist DELETE /api/watchlist/{ticker} returns 200', async ({ request }) => {
    // Use a direct API check as data-level evidence
    // First add JPM back in case a prior test removed it
    await request.post('/api/watchlist', { data: { ticker: 'JPM' } });

    const res = await request.delete('/api/watchlist/JPM');
    // Accept 200 or 204
    expect([200, 204]).toContain(res.status());

    // Re-add for consistency
    await request.post('/api/watchlist', { data: { ticker: 'JPM' } });
  });

  test('watchlist POST /api/watchlist with unknown ticker returns 400', async ({ request }) => {
    const res = await request.post('/api/watchlist', { data: { ticker: 'NOTREAL999' } });
    expect(res.status()).toBe(400);
  });
});
