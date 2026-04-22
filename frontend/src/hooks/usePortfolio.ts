'use client'

import { useState, useCallback } from 'react'
import { api } from '@/lib/api'
import type { Portfolio, PriceMap } from '@/lib/types'

export function usePortfolio() {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.getPortfolio()
      setPortfolio(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load portfolio')
    } finally {
      setLoading(false)
    }
  }, [])

  // Compute live total value from SSE prices × known quantities + cash
  const computeLiveValue = useCallback(
    (prices: PriceMap): number => {
      if (!portfolio) return 0
      let value = portfolio.cash_balance
      for (const position of portfolio.positions) {
        const livePrice = prices[position.ticker]?.price ?? position.current_price
        value += position.quantity * livePrice
      }
      return value
    },
    [portfolio]
  )

  return { portfolio, loading, error, refresh, computeLiveValue }
}
