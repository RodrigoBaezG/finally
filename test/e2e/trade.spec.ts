/**
 * Scenarios: Buy and Sell flows
 * - Buy shares: cash decreases, position appears
 * - Sell part of a position: row stays, quantity reduces
 * - Sell remaining: position row disappears
 * - Insufficient cash: error shown, no position created
 */
import { test, expect } from '@playwright/test';

test.describe('Trade flows', () => {
  test.beforeEach(async ({ page, request }) => {
    // Reset state: ensure no AAPL position and cash is at 10000
    // We do this by checking the portfolio; if there's an AAPL position sell it all
    const portfolio = await request.get('/api/portfolio');
    const body = await portfolio.json();
    const aaplPos = body.positions?.find((p: { ticker: string }) => p.ticker === 'AAPL');
    if (aaplPos) {
      await request.post('/api/portfolio/trade', {
        data: { ticker: 'AAPL', quantity: aaplPos.quantity, side: 'sell' },
      });
    }

    await page.goto('/');
    await expect(page.getByTestId('watchlist-row-AAPL')).toBeVisible({ timeout: 8000 });
  });

  test('buy 5 AAPL: cash decreases and position row appears', async ({ page, request }) => {
    const tickerInput = page.getByTestId('trade-ticker-input');
    const qtyInput = page.getByTestId('trade-qty-input');
    const buyBtn = page.getByTestId('trade-buy-btn');
    const cashEl = page.getByTestId('cash-balance');

    // Capture initial cash text
    await expect(cashEl).toBeVisible({ timeout: 5000 });
    const initialCashText = await cashEl.textContent();

    await tickerInput.fill('AAPL');
    await qtyInput.fill('5');
    await buyBtn.click();

    // Wait for position row to appear
    await expect(page.getByTestId('position-row-AAPL')).toBeVisible({ timeout: 10000 });

    // Cash should have decreased
    await expect.poll(
      async () => {
        const text = await cashEl.textContent();
        return text !== initialCashText;
      },
      { timeout: 8000 }
    ).toBe(true);

    // Verify via API
    const res = await request.get('/api/portfolio');
    expect(res.status()).toBe(200);
    const portfolio = await res.json();
    const aaplPos = portfolio.positions.find((p: { ticker: string }) => p.ticker === 'AAPL');
    expect(aaplPos).toBeDefined();
    expect(aaplPos.quantity).toBe(5);
    expect(portfolio.cash_balance).toBeLessThan(10000);
  });

  test('sell 2 of 5 AAPL: position row stays with reduced quantity', async ({ page, request }) => {
    // First buy 5 AAPL
    await request.post('/api/portfolio/trade', {
      data: { ticker: 'AAPL', quantity: 5, side: 'buy' },
    });

    await page.reload();
    await expect(page.getByTestId('watchlist-row-AAPL')).toBeVisible({ timeout: 8000 });
    await expect(page.getByTestId('position-row-AAPL')).toBeVisible({ timeout: 8000 });

    const tickerInput = page.getByTestId('trade-ticker-input');
    const qtyInput = page.getByTestId('trade-qty-input');
    const sellBtn = page.getByTestId('trade-sell-btn');

    await tickerInput.fill('AAPL');
    await qtyInput.fill('2');
    await sellBtn.click();

    // The AAPL position row should still be visible (3 shares remain)
    await expect(page.getByTestId('position-row-AAPL')).toBeVisible({ timeout: 8000 });

    // Verify via API that qty is now 3
    const res = await request.get('/api/portfolio');
    const portfolio = await res.json();
    const aaplPos = portfolio.positions.find((p: { ticker: string }) => p.ticker === 'AAPL');
    expect(aaplPos).toBeDefined();
    expect(aaplPos.quantity).toBe(3);
  });

  test('sell remaining AAPL shares: position row disappears', async ({ page, request }) => {
    // Ensure 3 AAPL shares (sell-2-of-5 leftover) or buy fresh 3
    const portRes = await request.get('/api/portfolio');
    const portBody = await portRes.json();
    const existing = portBody.positions.find((p: { ticker: string }) => p.ticker === 'AAPL');
    const heldQty = existing?.quantity ?? 0;

    if (heldQty === 0) {
      await request.post('/api/portfolio/trade', {
        data: { ticker: 'AAPL', quantity: 3, side: 'buy' },
      });
    }

    await page.reload();
    await expect(page.getByTestId('watchlist-row-AAPL')).toBeVisible({ timeout: 8000 });
    await expect(page.getByTestId('position-row-AAPL')).toBeVisible({ timeout: 8000 });

    // Get current held quantity
    const portRes2 = await request.get('/api/portfolio');
    const portBody2 = await portRes2.json();
    const qty = portBody2.positions.find((p: { ticker: string }) => p.ticker === 'AAPL')?.quantity ?? 3;

    const tickerInput = page.getByTestId('trade-ticker-input');
    const qtyInput = page.getByTestId('trade-qty-input');
    const sellBtn = page.getByTestId('trade-sell-btn');

    await tickerInput.fill('AAPL');
    await qtyInput.fill(String(qty));
    await sellBtn.click();

    // Position row should disappear
    await expect(page.getByTestId('position-row-AAPL')).not.toBeVisible({ timeout: 10000 });

    // Verify via API
    const finalRes = await request.get('/api/portfolio');
    const finalPortfolio = await finalRes.json();
    const aaplPos = finalPortfolio.positions.find((p: { ticker: string }) => p.ticker === 'AAPL');
    expect(aaplPos).toBeUndefined();
  });

  test('insufficient cash: buying 1000 NVDA shows error, no position created', async ({
    page,
    request,
  }) => {
    // NVDA seed price is $800; 1000 * 800 = $800,000 — way more than $10,000 cash
    const tickerInput = page.getByTestId('trade-ticker-input');
    const qtyInput = page.getByTestId('trade-qty-input');
    const buyBtn = page.getByTestId('trade-buy-btn');

    await tickerInput.fill('NVDA');
    await qtyInput.fill('1000');
    await buyBtn.click();

    // An error message should appear in the TradeBar
    // The TradeBar renders message.text in a div with class text-price-down
    const errorEl = page.locator('.text-price-down').first();
    await expect(errorEl).toBeVisible({ timeout: 8000 });
    const errorText = await errorEl.textContent();
    expect(errorText).toBeTruthy();

    // No NVDA position should be created
    const res = await request.get('/api/portfolio');
    const portfolio = await res.json();
    const nvdaPos = portfolio.positions.find((p: { ticker: string }) => p.ticker === 'NVDA');
    expect(nvdaPos).toBeUndefined();

    // Verify the trade API itself returns 400 for insufficient funds
    const tradeRes = await request.post('/api/portfolio/trade', {
      data: { ticker: 'NVDA', quantity: 1000, side: 'buy' },
    });
    expect(tradeRes.status()).toBe(400);
  });
});
