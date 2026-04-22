'use client'

import { useMemo } from 'react'
import type { Position, PriceMap } from '@/lib/types'
import { formatPercent, formatCurrency } from '@/lib/utils'

interface HeatmapCell {
  ticker: string
  weight: number  // 0..1 fraction of total position value
  pnlPercent: number
  currentPrice: number
  unrealizedPnl: number
  value: number
}

interface PortfolioHeatmapProps {
  positions: Position[]
  prices: PriceMap
  totalValue?: number
}

function pnlColor(pct: number): string {
  if (pct > 5) return '#166534'
  if (pct > 2) return '#15803d'
  if (pct > 0) return '#16a34a'
  if (pct < -5) return '#7f1d1d'
  if (pct < -2) return '#991b1b'
  if (pct < 0) return '#dc2626'
  return '#374151'
}

// Simple squarified treemap layout
function computeTreemap(
  cells: HeatmapCell[],
  x: number,
  y: number,
  w: number,
  h: number
): Array<HeatmapCell & { x: number; y: number; w: number; h: number }> {
  if (cells.length === 0) return []
  if (cells.length === 1) return [{ ...cells[0], x, y, w, h }]

  const totalWeight = cells.reduce((s, c) => s + c.weight, 0)
  const totalArea = w * h

  // Split into two halves by weight
  let acc = 0
  let splitIdx = 0
  for (let i = 0; i < cells.length; i++) {
    acc += cells[i].weight
    if (acc >= totalWeight / 2) {
      splitIdx = i + 1
      break
    }
  }

  const left = cells.slice(0, splitIdx)
  const right = cells.slice(splitIdx)
  const leftWeight = left.reduce((s, c) => s + c.weight, 0)
  const leftArea = (leftWeight / totalWeight) * totalArea

  if (w >= h) {
    const leftW = leftArea / h
    return [
      ...computeTreemap(left, x, y, leftW, h),
      ...computeTreemap(right, x + leftW, y, w - leftW, h),
    ]
  } else {
    const leftH = leftArea / w
    return [
      ...computeTreemap(left, x, y, w, leftH),
      ...computeTreemap(right, x, y + leftH, w, h - leftH),
    ]
  }
}

export function PortfolioHeatmap({ positions, prices }: PortfolioHeatmapProps) {
  const cells = useMemo<HeatmapCell[]>(() => {
    if (positions.length === 0) return []

    const totalPositionValue = positions.reduce((sum, p) => {
      const livePrice = prices[p.ticker]?.price ?? p.current_price
      return sum + p.quantity * livePrice
    }, 0)

    const base = totalPositionValue || 1

    return positions.map(p => {
      const livePrice = prices[p.ticker]?.price ?? p.current_price
      const value = p.quantity * livePrice
      const pnl = (livePrice - p.avg_cost) * p.quantity
      const pnlPct = ((livePrice - p.avg_cost) / p.avg_cost) * 100
      return {
        ticker: p.ticker,
        weight: value / base,
        pnlPercent: pnlPct,
        currentPrice: livePrice,
        unrealizedPnl: pnl,
        value,
      }
    }).sort((a, b) => b.weight - a.weight)
  }, [positions, prices])

  const layout = useMemo(
    () => computeTreemap(cells, 0, 0, 100, 100),
    [cells]
  )

  if (positions.length === 0) {
    return (
      <div className="flex flex-col h-full bg-bg-primary">
        <div className="px-3 py-2 border-b border-bg-border shrink-0">
          <span className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
            Portfolio Heatmap
          </span>
        </div>
        <div className="flex-1 flex items-center justify-center text-text-muted text-xs">
          No positions yet
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full bg-bg-primary">
      <div className="px-3 py-2 border-b border-bg-border flex items-center justify-between shrink-0">
        <span className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
          Portfolio Heatmap
        </span>
        <span className="text-xs text-text-muted">{positions.length} positions</span>
      </div>
      <div className="flex-1 relative min-h-0 p-1">
        <div className="absolute inset-1">
          {layout.map(cell => (
            <div
              key={cell.ticker}
              title={`${cell.ticker}: ${formatCurrency(cell.currentPrice)} | P&L: ${formatCurrency(cell.unrealizedPnl)} (${formatPercent(cell.pnlPercent)})`}
              style={{
                position: 'absolute',
                left: `${cell.x}%`,
                top: `${cell.y}%`,
                width: `${cell.w}%`,
                height: `${cell.h}%`,
                backgroundColor: pnlColor(cell.pnlPercent),
                border: '1px solid rgba(0,0,0,0.3)',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                overflow: 'hidden',
                padding: '2px',
              }}
            >
              {cell.w > 8 && cell.h > 6 && (
                <>
                  <span className="font-terminal font-bold text-white text-xs leading-tight">
                    {cell.ticker}
                  </span>
                  {cell.w > 12 && cell.h > 10 && (
                    <span
                      className={`font-terminal text-[10px] leading-tight ${
                        cell.pnlPercent >= 0 ? 'text-green-300' : 'text-red-300'
                      }`}
                    >
                      {formatPercent(cell.pnlPercent)}
                    </span>
                  )}
                </>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
