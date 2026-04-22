import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { WatchlistPanel } from '@/components/WatchlistPanel'
import type { WatchlistItem, PriceMap } from '@/lib/types'

// Mock the api module
vi.mock('@/lib/api', () => ({
  api: {
    addTicker: vi.fn(),
    removeTicker: vi.fn(),
  },
}))

import { api } from '@/lib/api'

const mockWatchlist: WatchlistItem[] = [
  {
    ticker: 'AAPL',
    price: 195.5,
    previous_price: 193.0,
    session_start_price: 190.0,
    session_change_percent: 2.89,
    direction: 'up',
  },
  {
    ticker: 'MSFT',
    price: 420.0,
    previous_price: 418.0,
    session_start_price: 415.0,
    session_change_percent: 1.2,
    direction: 'up',
  },
]

const mockPrices: PriceMap = {}
const mockSparklines = {}
const mockFlashMap = {}

const defaultProps = {
  watchlist: mockWatchlist,
  prices: mockPrices,
  sparklines: mockSparklines,
  flashMap: mockFlashMap,
  selectedTicker: null,
  onSelectTicker: vi.fn(),
  onWatchlistChange: vi.fn(),
}

describe('WatchlistPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders all watchlist tickers', () => {
    render(<WatchlistPanel {...defaultProps} />)
    expect(screen.getByTestId('watchlist-row-AAPL')).toBeInTheDocument()
    expect(screen.getByTestId('watchlist-row-MSFT')).toBeInTheDocument()
  })

  it('displays prices for each ticker', () => {
    render(<WatchlistPanel {...defaultProps} />)
    expect(screen.getByTestId('watchlist-price-AAPL')).toHaveTextContent('$195.50')
    expect(screen.getByTestId('watchlist-price-MSFT')).toHaveTextContent('$420.00')
  })

  it('calls onSelectTicker when a row is clicked', () => {
    const onSelect = vi.fn()
    render(<WatchlistPanel {...defaultProps} onSelectTicker={onSelect} />)
    fireEvent.click(screen.getByTestId('watchlist-row-AAPL'))
    expect(onSelect).toHaveBeenCalledWith('AAPL')
  })

  it('adds a ticker when form is submitted', async () => {
    vi.mocked(api.addTicker).mockResolvedValueOnce({
      ticker: 'TSLA',
      price: 300,
      previous_price: 295,
      session_start_price: 290,
      session_change_percent: 3.4,
      direction: 'up',
    })

    const onWatchlistChange = vi.fn()
    render(<WatchlistPanel {...defaultProps} onWatchlistChange={onWatchlistChange} />)

    const input = screen.getByTestId('add-ticker-input')
    fireEvent.change(input, { target: { value: 'TSLA' } })
    fireEvent.click(screen.getByTestId('add-ticker-btn'))

    await waitFor(() => {
      expect(api.addTicker).toHaveBeenCalledWith('TSLA')
      expect(onWatchlistChange).toHaveBeenCalled()
    })
  })

  it('shows error message when adding fails', async () => {
    vi.mocked(api.addTicker).mockRejectedValueOnce(new Error('Ticker not found'))

    render(<WatchlistPanel {...defaultProps} />)

    const input = screen.getByTestId('add-ticker-input')
    fireEvent.change(input, { target: { value: 'INVALID' } })
    fireEvent.click(screen.getByTestId('add-ticker-btn'))

    await waitFor(() => {
      expect(screen.getByText('Ticker not found')).toBeInTheDocument()
    })
  })

  it('removes a ticker when remove button is clicked', async () => {
    vi.mocked(api.removeTicker).mockResolvedValueOnce(undefined)
    const onWatchlistChange = vi.fn()

    render(<WatchlistPanel {...defaultProps} onWatchlistChange={onWatchlistChange} />)

    fireEvent.click(screen.getByTestId('remove-ticker-btn-AAPL'))

    await waitFor(() => {
      expect(api.removeTicker).toHaveBeenCalledWith('AAPL')
      expect(onWatchlistChange).toHaveBeenCalled()
    })
  })

  it('highlights selected ticker', () => {
    render(<WatchlistPanel {...defaultProps} selectedTicker="AAPL" />)
    const row = screen.getByTestId('watchlist-row-AAPL')
    expect(row.className).toContain('bg-bg-elevated')
  })

  it('shows empty state when watchlist is empty', () => {
    render(<WatchlistPanel {...defaultProps} watchlist={[]} />)
    expect(screen.getByText('No tickers in watchlist')).toBeInTheDocument()
  })

  it('live price overrides static price from SSE', () => {
    const prices: PriceMap = {
      AAPL: {
        ticker: 'AAPL',
        price: 199.99,
        previous_price: 195.5,
        session_start_price: 190,
        timestamp: Date.now() / 1000,
        change: 4.49,
        change_percent: 2.3,
        session_change_percent: 5.26,
        direction: 'up',
      },
    }
    render(<WatchlistPanel {...defaultProps} prices={prices} />)
    expect(screen.getByTestId('watchlist-price-AAPL')).toHaveTextContent('$199.99')
  })
})
