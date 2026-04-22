import { describe, it, expect } from 'vitest'
import type { Portfolio, PriceMap } from '@/lib/types'

// Test the portfolio live value calculation logic (mirrors usePortfolio.computeLiveValue)
function computeLiveValue(portfolio: Portfolio, prices: PriceMap): number {
  let value = portfolio.cash_balance
  for (const position of portfolio.positions) {
    const livePrice = prices[position.ticker]?.price ?? position.current_price
    value += position.quantity * livePrice
  }
  return value
}

const basePortfolio: Portfolio = {
  cash_balance: 5000,
  total_value: 10000,
  total_unrealized_pnl: 0,
  positions: [
    {
      ticker: 'AAPL',
      quantity: 10,
      avg_cost: 190,
      current_price: 195,
      unrealized_pnl: 50,
      pnl_percent: 2.63,
    },
    {
      ticker: 'MSFT',
      quantity: 5,
      avg_cost: 380,
      current_price: 390,
      unrealized_pnl: 50,
      pnl_percent: 2.63,
    },
  ],
}

describe('Portfolio live value calculation', () => {
  it('computes value with no price overrides using current_price', () => {
    const value = computeLiveValue(basePortfolio, {})
    // 5000 cash + 10*195 + 5*390 = 5000 + 1950 + 1950 = 8900
    expect(value).toBe(8900)
  })

  it('uses live SSE price when available', () => {
    const prices: PriceMap = {
      AAPL: {
        ticker: 'AAPL',
        price: 200,
        previous_price: 195,
        session_start_price: 190,
        timestamp: Date.now() / 1000,
        change: 5,
        change_percent: 2.56,
        session_change_percent: 5.26,
        direction: 'up',
      },
    }
    const value = computeLiveValue(basePortfolio, prices)
    // 5000 + 10*200 + 5*390 = 5000 + 2000 + 1950 = 8950
    expect(value).toBe(8950)
  })

  it('handles empty positions', () => {
    const empty: Portfolio = {
      ...basePortfolio,
      positions: [],
      cash_balance: 10000,
    }
    expect(computeLiveValue(empty, {})).toBe(10000)
  })

  it('computes correct unrealized P&L per position', () => {
    const pos = basePortfolio.positions[0]
    const livePrice = 200
    const unrPnl = (livePrice - pos.avg_cost) * pos.quantity
    expect(unrPnl).toBe(100) // (200-190)*10
  })

  it('handles fractional shares', () => {
    const portfolio: Portfolio = {
      ...basePortfolio,
      positions: [
        {
          ticker: 'AAPL',
          quantity: 2.5,
          avg_cost: 100,
          current_price: 110,
          unrealized_pnl: 25,
          pnl_percent: 10,
        },
      ],
      cash_balance: 0,
    }
    const value = computeLiveValue(portfolio, {})
    // 0 + 2.5 * 110 = 275
    expect(value).toBe(275)
  })
})

describe('P&L calculations', () => {
  it('calculates positive P&L percentage correctly', () => {
    const avgCost = 100
    const currentPrice = 110
    const pnlPct = ((currentPrice - avgCost) / avgCost) * 100
    expect(pnlPct).toBe(10)
  })

  it('calculates negative P&L percentage correctly', () => {
    const avgCost = 200
    const currentPrice = 150
    const pnlPct = ((currentPrice - avgCost) / avgCost) * 100
    expect(pnlPct).toBe(-25)
  })

  it('session change percent from SSE data', () => {
    const sessionStartPrice = 190
    const currentPrice = 200
    const sessionChange = ((currentPrice - sessionStartPrice) / sessionStartPrice) * 100
    expect(sessionChange).toBeCloseTo(5.26, 1)
  })
})
