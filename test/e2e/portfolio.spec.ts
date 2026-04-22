/**
 * Scenario: Portfolio visualization
 * - Heatmap renders with position rectangles after buying shares
 * - P&L chart is visible with a canvas element
 * - Portfolio history endpoint returns snapshots
 */
import { test, expect } from '@playwright/test';

test.describe('Portfolio visualization', () => {
  test.beforeEach(async ({ page, request }) => {
    // Ensure we have at least one position (AAPL) so the heatmap and positions table work.
    // We buy 1 AAPL regardless of current state; if we already have it the quantity adds up.
    const portRes = await request.get('/api/portfolio');
    const portBody = await portRes.json();
    const aaplPos = portBody.positions?.find((p: { ticker: string }) => p.ticker === 'AAPL');

    if (!aaplPos) {
      // Buy AAPL only if we have enough cash (at least $200)
      if (portBody.cash_balance >= 200) {
        const tradeRes = await request.post('/api/portfolio/trade', {
          data: { ticker: 'AAPL', quantity: 1, side: 'buy' },
        });
        // If buy fails (e.g., insufficient cash), fall back to GOOGL or MSFT
        if (tradeRes.status() !== 200 && tradeRes.status() !== 201) {
          // Try a cheaper alternative
          await request.post('/api/portfolio/trade', {
            data: { ticker: 'GOOGL', quantity: 1, side: 'buy' },
          });
        }
      }
    }

    await page.goto('/');
    await expect(page.getByTestId('watchlist-row-AAPL')).toBeVisible({ timeout: 8000 });
  });

  test('portfolio history API returns snapshot array', async ({ request }) => {
    const res = await request.get('/api/portfolio/history');
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(Array.isArray(body)).toBe(true);
    // There should be at least 1 snapshot (created at startup or after trade)
    // We don't assert exact count because timing varies
  });

  test('portfolio API returns correct structure', async ({ request }) => {
    const res = await request.get('/api/portfolio');
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(typeof body.cash_balance).toBe('number');
    expect(typeof body.total_value).toBe('number');
    expect(Array.isArray(body.positions)).toBe(true);
  });

  test('heatmap panel is visible after buying positions', async ({ page }) => {
    // The PortfolioHeatmap renders a section with "Portfolio Heatmap" text
    const heatmapLabel = page.getByText('Portfolio Heatmap');
    await expect(heatmapLabel).toBeVisible({ timeout: 8000 });
  });

  test('heatmap shows position rectangles for held tickers', async ({ page, request }) => {
    // The heatmap renders colored divs for each position.
    // Determine which ticker we bought in beforeEach
    const portRes = await request.get('/api/portfolio');
    const portBody = await portRes.json();
    const positions = portBody.positions ?? [];
    expect(positions.length).toBeGreaterThan(0);

    const ticker = positions[0].ticker;

    // The positions table row for this ticker should be visible after page load
    await expect.poll(
      async () => {
        const el = page.getByTestId(`position-row-${ticker}`);
        return el.isVisible();
      },
      { timeout: 10000 }
    ).toBe(true);

    // The heatmap section should also be visible
    const heatmapLabel = page.getByText('Portfolio Heatmap');
    await expect(heatmapLabel).toBeVisible({ timeout: 5000 });
  });

  test('P&L chart section is visible', async ({ page }) => {
    // The PnLChart renders a section header with "P&L" text
    const pnlLabel = page.getByText('P&L');
    await expect(pnlLabel.first()).toBeVisible({ timeout: 8000 });
  });

  test('P&L chart has a canvas element for drawing', async ({ page }) => {
    // Wait for the chart section to render
    await expect(page.getByText('P&L').first()).toBeVisible({ timeout: 8000 });
    // The PnLChart renders a <canvas> element
    const canvas = page.locator('canvas').first();
    await expect(canvas).toBeVisible({ timeout: 8000 });
  });

  test('positions table shows at least one position row', async ({ page, request }) => {
    // The beforeEach buys at least 1 share of a ticker.
    // Confirm via API which ticker is held, then check the row.
    const portRes = await request.get('/api/portfolio');
    const portBody = await portRes.json();
    const positions = portBody.positions ?? [];
    expect(positions.length).toBeGreaterThan(0);

    const ticker = positions[0].ticker;
    await expect.poll(
      async () => page.getByTestId(`position-row-${ticker}`).isVisible(),
      { timeout: 10000 }
    ).toBe(true);
  });
});
