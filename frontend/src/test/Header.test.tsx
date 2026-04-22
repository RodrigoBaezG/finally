import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Header } from '@/components/Header'

describe('Header', () => {
  it('renders portfolio total value', () => {
    render(<Header status="connected" portfolioTotal={12345.67} cashBalance={5000} />)
    expect(screen.getByTestId('portfolio-total')).toHaveTextContent('$12,345.67')
  })

  it('renders cash balance', () => {
    render(<Header status="connected" portfolioTotal={10000} cashBalance={3500.25} />)
    expect(screen.getByTestId('cash-balance')).toHaveTextContent('$3,500.25')
  })

  it('shows connected status dot with data-status="connected"', () => {
    render(<Header status="connected" portfolioTotal={10000} cashBalance={5000} />)
    const dot = screen.getByTestId('connection-status')
    expect(dot).toHaveAttribute('data-status', 'connected')
  })

  it('shows disconnected status dot with data-status="disconnected"', () => {
    render(<Header status="disconnected" portfolioTotal={10000} cashBalance={5000} />)
    const dot = screen.getByTestId('connection-status')
    expect(dot).toHaveAttribute('data-status', 'disconnected')
  })

  it('renders the brand name', () => {
    render(<Header status="connected" portfolioTotal={0} cashBalance={0} />)
    expect(screen.getByText('FIN')).toBeInTheDocument()
    expect(screen.getByText('ALLY')).toBeInTheDocument()
  })
})
