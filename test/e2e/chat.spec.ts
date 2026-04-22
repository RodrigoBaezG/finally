/**
 * Scenarios: AI Chat (mock mode)
 * - Send "buy 3 MSFT" → chat reply appears, trade confirmation visible, MSFT position created
 * - Send "remove META from watchlist" → META row disappears
 * - Chat API returns expected structured response
 */
import { test, expect } from '@playwright/test';

test.describe('AI Chat (LLM mock)', () => {
  test.beforeEach(async ({ page, request }) => {
    // Clean up: sell any existing MSFT position so tests start clean
    const portRes = await request.get('/api/portfolio');
    const portBody = await portRes.json();
    const msftPos = portBody.positions?.find((p: { ticker: string }) => p.ticker === 'MSFT');
    if (msftPos) {
      await request.post('/api/portfolio/trade', {
        data: { ticker: 'MSFT', quantity: msftPos.quantity, side: 'sell' },
      });
    }

    // Ensure META is on watchlist
    await request.post('/api/watchlist', { data: { ticker: 'META' } });

    await page.goto('/');
    await expect(page.getByTestId('watchlist-row-AAPL')).toBeVisible({ timeout: 8000 });
  });

  test('chat API returns structured mock response for buy command', async ({ request }) => {
    const res = await request.post('/api/chat', {
      data: { message: 'buy 3 MSFT' },
    });
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(typeof body.message).toBe('string');
    expect(body.message.length).toBeGreaterThan(0);
    expect(Array.isArray(body.trades)).toBe(true);
    const msftTrade = body.trades.find(
      (t: { ticker: string; side: string }) => t.ticker === 'MSFT' && t.side === 'buy'
    );
    expect(msftTrade).toBeDefined();
    expect(msftTrade.status).toBe('executed');
  });

  test('send "buy 3 MSFT" in chat UI: assistant reply appears with trade confirmation', async ({
    page,
    request,
  }) => {
    const chatInput = page.getByTestId('chat-input');
    const chatSend = page.getByTestId('chat-send');

    await expect(chatInput).toBeVisible({ timeout: 5000 });
    await chatInput.fill('buy 3 MSFT');
    await chatSend.click();

    // User message should appear
    await expect(page.getByTestId('chat-message-user').first()).toBeVisible({ timeout: 8000 });

    // Assistant message should appear
    await expect(page.getByTestId('chat-message-assistant').first()).toBeVisible({
      timeout: 15000,
    });

    // Trade confirmation box should be visible in the chat (green box for buy)
    // The TradeConfirmation component renders a div with text "Bought 3x MSFT"
    const tradeConfirmation = page.locator('text=MSFT').first();
    await expect(tradeConfirmation).toBeVisible({ timeout: 8000 });

    // Verify MSFT position was created via API
    const res = await request.get('/api/portfolio');
    const portfolio = await res.json();
    const msftPos = portfolio.positions.find((p: { ticker: string }) => p.ticker === 'MSFT');
    expect(msftPos).toBeDefined();
    expect(msftPos.quantity).toBe(3);
  });

  test('send "remove META from watchlist" in chat UI: META row disappears', async ({
    page,
    request,
  }) => {
    // Ensure META is in the watchlist
    await expect(page.getByTestId('watchlist-row-META')).toBeVisible({ timeout: 8000 });

    const chatInput = page.getByTestId('chat-input');
    const chatSend = page.getByTestId('chat-send');

    await chatInput.fill('remove META from watchlist');
    await chatSend.click();

    // Assistant message should appear
    await expect(page.getByTestId('chat-message-assistant').first()).toBeVisible({
      timeout: 15000,
    });

    // META should no longer be in the watchlist
    await expect(page.getByTestId('watchlist-row-META')).not.toBeVisible({ timeout: 10000 });

    // Verify via API
    const res = await request.get('/api/watchlist');
    const body = await res.json();
    const tickers = body.map((item: { ticker: string }) => item.ticker);
    expect(tickers).not.toContain('META');

    // Cleanup: re-add META
    await request.post('/api/watchlist', { data: { ticker: 'META' } });
  });

  test('chat sends message via Enter key and shows response', async ({ page }) => {
    const chatInput = page.getByTestId('chat-input');

    await expect(chatInput).toBeVisible({ timeout: 5000 });
    await chatInput.fill('hello');
    await chatInput.press('Enter');

    // User and assistant messages should appear
    await expect(page.getByTestId('chat-message-user').first()).toBeVisible({ timeout: 8000 });
    await expect(page.getByTestId('chat-message-assistant').first()).toBeVisible({
      timeout: 15000,
    });
  });
});
