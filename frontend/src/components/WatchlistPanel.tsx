'use client'

import { useState, useCallback } from 'react'
import { Sparkline } from './Sparkline'
import { formatCurrency, formatPercent } from '@/lib/utils'
import type { PriceMap, SparklineData, WatchlistItem } from '@/lib/types'
import { api } from '@/lib/api'

interface WatchlistPanelProps {
  watchlist: WatchlistItem[]
  prices: PriceMap
  sparklines: Record<string, SparklineData>
  flashMap: Record<string, 'up' | 'down' | null>
  selectedTicker: string | null
  onSelectTicker: (ticker: string) => void
  onWatchlistChange: () => void
}

export function WatchlistPanel({
  watchlist,
  prices,
  sparklines,
  flashMap,
  selectedTicker,
  onSelectTicker,
  onWatchlistChange,
}: WatchlistPanelProps) {
  const [addInput, setAddInput] = useState('')
  const [addError, setAddError] = useState<string | null>(null)
  const [addLoading, setAddLoading] = useState(false)

  const handleAdd = useCallback(async () => {
    const ticker = addInput.trim().toUpperCase()
    if (!ticker) return
    setAddLoading(true)
    setAddError(null)
    try {
      await api.addTicker(ticker)
      setAddInput('')
      onWatchlistChange()
    } catch (err) {
      setAddError(err instanceof Error ? err.message : 'Failed to add ticker')
    } finally {
      setAddLoading(false)
    }
  }, [addInput, onWatchlistChange])

  const handleRemove = useCallback(
    async (ticker: string) => {
      try {
        await api.removeTicker(ticker)
        onWatchlistChange()
      } catch {
        // silently ignore
      }
    },
    [onWatchlistChange]
  )

  const handleAddKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleAdd()
  }

  return (
    <div className="flex flex-col h-full bg-bg-secondary border-r border-bg-border">
      {/* Panel header */}
      <div className="px-3 py-2 border-b border-bg-border flex items-center justify-between shrink-0">
        <span className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
          Watchlist
        </span>
        <span className="text-xs text-text-muted">{watchlist.length} tickers</span>
      </div>

      {/* Add ticker */}
      <div className="px-3 py-2 border-b border-bg-border shrink-0">
        <div className="flex gap-1">
          <input
            type="text"
            value={addInput}
            onChange={e => setAddInput(e.target.value.toUpperCase())}
            onKeyDown={handleAddKeyDown}
            placeholder="Add ticker..."
            className="flex-1 bg-bg-primary border border-bg-border rounded px-2 py-1 text-xs text-text-primary placeholder-text-muted focus:outline-none focus:border-accent-blue font-terminal uppercase"
            data-testid="add-ticker-input"
            disabled={addLoading}
          />
          <button
            onClick={handleAdd}
            disabled={addLoading || !addInput.trim()}
            className="bg-accent-blue hover:bg-blue-500 disabled:opacity-40 text-white text-xs px-2 py-1 rounded font-semibold transition-colors"
            data-testid="add-ticker-btn"
          >
            +
          </button>
        </div>
        {addError && (
          <div className="text-price-down text-xs mt-1 truncate">{addError}</div>
        )}
      </div>

      {/* Column headers */}
      <div className="grid grid-cols-[auto_1fr_auto_auto] gap-1 px-3 py-1 border-b border-bg-border shrink-0">
        <span className="text-text-muted text-xs">SYM</span>
        <span className="text-text-muted text-xs text-right">PRICE</span>
        <span className="text-text-muted text-xs text-right">CHG%</span>
        <span className="w-4" />
      </div>

      {/* Ticker rows */}
      <div className="flex-1 overflow-y-auto">
        {watchlist.map(item => {
          const live = prices[item.ticker]
          const price = live?.price ?? item.price
          const sessionChg = live?.session_change_percent ?? item.session_change_percent
          const flash = flashMap[item.ticker]
          const spark = sparklines[item.ticker] ?? []
          const isSelected = selectedTicker === item.ticker

          return (
            <div
              key={item.ticker}
              data-testid={`watchlist-row-${item.ticker}`}
              onClick={() => onSelectTicker(item.ticker)}
              className={`
                grid grid-cols-[auto_1fr_auto_auto] gap-1 items-center px-3 py-1.5
                cursor-pointer border-b border-bg-border hover:bg-bg-elevated transition-colors
                ${isSelected ? 'bg-bg-elevated border-l-2 border-l-accent-blue' : ''}
                ${flash === 'up' ? 'price-flash-up' : flash === 'down' ? 'price-flash-down' : ''}
              `}
            >
              {/* Ticker symbol */}
              <div className="min-w-[44px]">
                <div className="text-xs font-semibold font-terminal text-text-primary">
                  {item.ticker}
                </div>
                <div className="mt-0.5">
                  <Sparkline data={spark} width={56} height={20} />
                </div>
              </div>

              {/* Price */}
              <div
                className="text-right"
                data-testid={`watchlist-price-${item.ticker}`}
              >
                <span
                  className={`text-xs font-terminal font-medium ${
                    flash === 'up'
                      ? 'text-price-up'
                      : flash === 'down'
                      ? 'text-price-down'
                      : 'text-text-primary'
                  }`}
                >
                  {formatCurrency(price)}
                </span>
              </div>

              {/* Session change % */}
              <div className="text-right min-w-[52px]">
                <span
                  className={`text-xs font-terminal ${
                    sessionChg >= 0 ? 'text-price-up' : 'text-price-down'
                  }`}
                >
                  {formatPercent(sessionChg)}
                </span>
              </div>

              {/* Remove button */}
              <button
                onClick={e => {
                  e.stopPropagation()
                  handleRemove(item.ticker)
                }}
                className="text-text-muted hover:text-price-down text-xs w-4 text-center transition-colors"
                data-testid={`remove-ticker-btn-${item.ticker}`}
                aria-label={`Remove ${item.ticker}`}
              >
                ×
              </button>
            </div>
          )
        })}
        {watchlist.length === 0 && (
          <div className="px-3 py-4 text-text-muted text-xs text-center">
            No tickers in watchlist
          </div>
        )}
      </div>
    </div>
  )
}
