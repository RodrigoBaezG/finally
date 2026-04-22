'use client'

import type { Position, PriceMap } from '@/lib/types'
import { formatCurrency, formatPercent } from '@/lib/utils'

interface PositionsTableProps {
  positions: Position[]
  prices: PriceMap
}

export function PositionsTable({ positions, prices }: PositionsTableProps) {
  return (
    <div className="flex flex-col h-full bg-bg-primary">
      <div className="px-3 py-2 border-b border-bg-border shrink-0">
        <span className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
          Positions
        </span>
      </div>
      <div className="flex-1 overflow-auto min-h-0">
        <table className="w-full text-xs font-terminal">
          <thead className="sticky top-0 bg-bg-secondary z-10">
            <tr className="text-text-muted uppercase tracking-wider">
              <th className="text-left px-3 py-1.5">Ticker</th>
              <th className="text-right px-2 py-1.5">Qty</th>
              <th className="text-right px-2 py-1.5">Avg Cost</th>
              <th className="text-right px-2 py-1.5">Price</th>
              <th className="text-right px-2 py-1.5">Unrlzd P&amp;L</th>
              <th className="text-right px-3 py-1.5">% Chg</th>
            </tr>
          </thead>
          <tbody>
            {positions.length === 0 && (
              <tr>
                <td colSpan={6} className="text-center py-4 text-text-muted">
                  No positions
                </td>
              </tr>
            )}
            {positions.map(pos => {
              const livePrice = prices[pos.ticker]?.price ?? pos.current_price
              const unrPnl = (livePrice - pos.avg_cost) * pos.quantity
              const pnlPct = ((livePrice - pos.avg_cost) / pos.avg_cost) * 100
              const isPositive = unrPnl >= 0

              return (
                <tr
                  key={pos.ticker}
                  data-testid={`position-row-${pos.ticker}`}
                  className="border-b border-bg-border hover:bg-bg-elevated transition-colors"
                >
                  <td className="px-3 py-1.5 font-semibold text-text-primary">
                    {pos.ticker}
                  </td>
                  <td className="text-right px-2 py-1.5 text-text-secondary">
                    {pos.quantity % 1 === 0
                      ? pos.quantity.toFixed(0)
                      : pos.quantity.toFixed(2)}
                  </td>
                  <td className="text-right px-2 py-1.5 text-text-secondary">
                    {formatCurrency(pos.avg_cost)}
                  </td>
                  <td className="text-right px-2 py-1.5 text-text-primary">
                    {formatCurrency(livePrice)}
                  </td>
                  <td
                    className={`text-right px-2 py-1.5 font-medium ${
                      isPositive ? 'text-price-up' : 'text-price-down'
                    }`}
                  >
                    {isPositive ? '+' : ''}{formatCurrency(unrPnl)}
                  </td>
                  <td
                    className={`text-right px-3 py-1.5 ${
                      isPositive ? 'text-price-up' : 'text-price-down'
                    }`}
                  >
                    {formatPercent(pnlPct)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
