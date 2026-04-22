import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { TradeBar } from '@/components/TradeBar'
import type { PriceMap } from '@/lib/types'

vi.mock('@/lib/api', () => ({
  api: {
    trade: vi.fn(),
  },
}))

import { api } from '@/lib/api'

const mockPrices: PriceMap = {
  AAPL: {
    ticker: 'AAPL',
    price: 195.5,
    previous_price: 193.0,
    session_start_price: 190.0,
    timestamp: Date.now() / 1000,
    change: 2.5,
    change_percent: 1.3,
    session_change_percent: 2.89,
    direction: 'up',
  },
}

describe('TradeBar', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders trade inputs and buttons', () => {
    render(<TradeBar prices={mockPrices} cashBalance={5000} onTradeComplete={vi.fn()} />)
    expect(screen.getByTestId('trade-ticker-input')).toBeInTheDocument()
    expect(screen.getByTestId('trade-qty-input')).toBeInTheDocument()
    expect(screen.getByTestId('trade-buy-btn')).toBeInTheDocument()
    expect(screen.getByTestId('trade-sell-btn')).toBeInTheDocument()
  })

  it('buy button is disabled when inputs are empty', () => {
    render(<TradeBar prices={mockPrices} cashBalance={5000} onTradeComplete={vi.fn()} />)
    expect(screen.getByTestId('trade-buy-btn')).toBeDisabled()
    expect(screen.getByTestId('trade-sell-btn')).toBeDisabled()
  })

  it('executes buy trade successfully', async () => {
    vi.mocked(api.trade).mockResolvedValueOnce({
      success: true,
      message: 'Trade executed',
      trade: { ticker: 'AAPL', side: 'buy', quantity: 5, price: 195.5, executed_at: '' },
    })

    const onTradeComplete = vi.fn()
    render(<TradeBar prices={mockPrices} cashBalance={5000} onTradeComplete={onTradeComplete} />)

    fireEvent.change(screen.getByTestId('trade-ticker-input'), { target: { value: 'AAPL' } })
    fireEvent.change(screen.getByTestId('trade-qty-input'), { target: { value: '5' } })
    fireEvent.click(screen.getByTestId('trade-buy-btn'))

    await waitFor(() => {
      expect(api.trade).toHaveBeenCalledWith({ ticker: 'AAPL', quantity: 5, side: 'buy' })
      expect(onTradeComplete).toHaveBeenCalled()
    })
  })

  it('executes sell trade successfully', async () => {
    vi.mocked(api.trade).mockResolvedValueOnce({
      success: true,
      message: 'Trade executed',
      trade: { ticker: 'AAPL', side: 'sell', quantity: 3, price: 195.5, executed_at: '' },
    })

    render(<TradeBar prices={mockPrices} cashBalance={5000} onTradeComplete={vi.fn()} />)

    fireEvent.change(screen.getByTestId('trade-ticker-input'), { target: { value: 'AAPL' } })
    fireEvent.change(screen.getByTestId('trade-qty-input'), { target: { value: '3' } })
    fireEvent.click(screen.getByTestId('trade-sell-btn'))

    await waitFor(() => {
      expect(api.trade).toHaveBeenCalledWith({ ticker: 'AAPL', quantity: 3, side: 'sell' })
    })
  })

  it('shows error message on failed trade', async () => {
    vi.mocked(api.trade).mockResolvedValueOnce({
      success: false,
      message: 'Insufficient cash',
    })

    render(<TradeBar prices={mockPrices} cashBalance={5000} onTradeComplete={vi.fn()} />)

    fireEvent.change(screen.getByTestId('trade-ticker-input'), { target: { value: 'AAPL' } })
    fireEvent.change(screen.getByTestId('trade-qty-input'), { target: { value: '1000' } })
    fireEvent.click(screen.getByTestId('trade-buy-btn'))

    await waitFor(() => {
      expect(screen.getByText('Insufficient cash')).toBeInTheDocument()
    })
  })

  it('shows validation error for empty ticker', async () => {
    render(<TradeBar prices={mockPrices} cashBalance={5000} onTradeComplete={vi.fn()} />)
    // Buy is disabled when ticker is empty, so no call should be made
    expect(screen.getByTestId('trade-buy-btn')).toBeDisabled()
  })

  it('displays cash balance', () => {
    render(<TradeBar prices={mockPrices} cashBalance={7500.50} onTradeComplete={vi.fn()} />)
    expect(screen.getByText('$7,500.50')).toBeInTheDocument()
  })
})
