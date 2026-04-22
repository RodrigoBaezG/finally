import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PositionsTable } from '@/components/PositionsTable'
import type { Position, PriceMap } from '@/lib/types'

const mockPositions: Position[] = [
  {
    ticker: 'AAPL',
    quantity: 10,
    avg_cost: 190,
    current_price: 200,
    unrealized_pnl: 100,
    pnl_percent: 5.26,
  },
  {
    ticker: 'TSLA',
    quantity: 5,
    avg_cost: 300,
    current_price: 280,
    unrealized_pnl: -100,
    pnl_percent: -6.67,
  },
]

describe('PositionsTable', () => {
  it('renders position rows for each ticker', () => {
    render(<PositionsTable positions={mockPositions} prices={{}} />)
    expect(screen.getByTestId('position-row-AAPL')).toBeInTheDocument()
    expect(screen.getByTestId('position-row-TSLA')).toBeInTheDocument()
  })

  it('shows empty state when no positions', () => {
    render(<PositionsTable positions={[]} prices={{}} />)
    expect(screen.getByText('No positions')).toBeInTheDocument()
  })

  it('uses live price from SSE when available', () => {
    const prices: PriceMap = {
      AAPL: {
        ticker: 'AAPL',
        price: 205,
        previous_price: 200,
        session_start_price: 190,
        timestamp: Date.now() / 1000,
        change: 5,
        change_percent: 2.5,
        session_change_percent: 7.89,
        direction: 'up',
      },
    }
    render(<PositionsTable positions={mockPositions} prices={prices} />)
    const row = screen.getByTestId('position-row-AAPL')
    expect(row).toHaveTextContent('$205.00')
  })
})
