'use client'

import { useState } from 'react'
import { api } from '@/lib/api'
import type { PriceMap } from '@/lib/types'
import { formatCurrency } from '@/lib/utils'

interface TradeBarProps {
  prices: PriceMap
  cashBalance: number
  onTradeComplete: () => void
}

export function TradeBar({ prices, cashBalance, onTradeComplete }: TradeBarProps) {
  const [ticker, setTicker] = useState('')
  const [quantity, setQuantity] = useState('')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null)

  const currentPrice = ticker ? (prices[ticker.toUpperCase()]?.price ?? null) : null
  const estimatedCost =
    currentPrice !== null && quantity ? currentPrice * parseFloat(quantity) : null

  const executeTrade = async (side: 'buy' | 'sell') => {
    const sym = ticker.trim().toUpperCase()
    const qty = parseFloat(quantity)
    if (!sym || isNaN(qty) || qty <= 0) {
      setMessage({ text: 'Enter a valid ticker and quantity', type: 'error' })
      return
    }
    setLoading(true)
    setMessage(null)
    try {
      const result = await api.trade({ ticker: sym, quantity: qty, side })
      if (result.success) {
        setMessage({
          text: `${side === 'buy' ? 'Bought' : 'Sold'} ${qty} ${sym} @ ${formatCurrency(result.trade?.price ?? 0)}`,
          type: 'success',
        })
        setQuantity('')
        onTradeComplete()
      } else {
        setMessage({ text: result.message, type: 'error' })
      }
    } catch (err) {
      setMessage({
        text: err instanceof Error ? err.message : 'Trade failed',
        type: 'error',
      })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="bg-bg-secondary border-t border-bg-border px-3 py-2 shrink-0">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-text-muted text-xs uppercase tracking-wider font-semibold">
          Trade
        </span>

        <input
          type="text"
          value={ticker}
          onChange={e => setTicker(e.target.value.toUpperCase())}
          placeholder="TICKER"
          className="w-24 bg-bg-primary border border-bg-border rounded px-2 py-1 text-xs font-terminal text-text-primary placeholder-text-muted focus:outline-none focus:border-accent-blue uppercase"
          data-testid="trade-ticker-input"
          disabled={loading}
        />

        <input
          type="number"
          value={quantity}
          onChange={e => setQuantity(e.target.value)}
          placeholder="Qty"
          min="0.01"
          step="1"
          className="w-20 bg-bg-primary border border-bg-border rounded px-2 py-1 text-xs font-terminal text-text-primary placeholder-text-muted focus:outline-none focus:border-accent-blue"
          data-testid="trade-qty-input"
          disabled={loading}
        />

        {currentPrice !== null && (
          <span className="text-text-muted text-xs font-terminal">
            @{formatCurrency(currentPrice)}
            {estimatedCost !== null && (
              <span className="text-text-secondary"> ≈ {formatCurrency(estimatedCost)}</span>
            )}
          </span>
        )}

        <button
          onClick={() => executeTrade('buy')}
          disabled={loading || !ticker.trim() || !quantity}
          className="bg-price-up hover:bg-green-600 disabled:opacity-40 text-white text-xs px-3 py-1 rounded font-semibold transition-colors"
          data-testid="trade-buy-btn"
        >
          BUY
        </button>

        <button
          onClick={() => executeTrade('sell')}
          disabled={loading || !ticker.trim() || !quantity}
          className="bg-price-down hover:bg-red-600 disabled:opacity-40 text-white text-xs px-3 py-1 rounded font-semibold transition-colors"
          data-testid="trade-sell-btn"
        >
          SELL
        </button>

        <div className="ml-auto flex items-center gap-3">
          <span className="text-text-muted text-xs">Cash:</span>
          <span className="font-terminal text-xs text-text-primary font-medium">
            {formatCurrency(cashBalance)}
          </span>
        </div>
      </div>

      {message && (
        <div
          className={`mt-1 text-xs font-terminal ${
            message.type === 'success' ? 'text-price-up' : 'text-price-down'
          }`}
        >
          {message.text}
        </div>
      )}
    </div>
  )
}
