'use client'

import { useEffect, useRef, useCallback } from 'react'
import type { PortfolioSnapshot } from '@/lib/types'
import { formatCurrency } from '@/lib/utils'

interface PnLChartProps {
  history: PortfolioSnapshot[]
}

export function PnLChart({ history }: PnLChartProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  const drawChart = useCallback(() => {
    const canvas = canvasRef.current
    const container = containerRef.current
    if (!canvas || !container) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const dpr = window.devicePixelRatio ?? 1
    const w = container.clientWidth
    const h = container.clientHeight
    canvas.width = w * dpr
    canvas.height = h * dpr
    canvas.style.width = `${w}px`
    canvas.style.height = `${h}px`
    ctx.scale(dpr, dpr)

    ctx.fillStyle = '#0d1117'
    ctx.fillRect(0, 0, w, h)

    if (history.length < 2) {
      ctx.fillStyle = '#64748b'
      ctx.font = '12px Inter, sans-serif'
      ctx.textAlign = 'center'
      ctx.fillText('Collecting portfolio history...', w / 2, h / 2)
      return
    }

    const values = history.map(s => s.total_value)
    const minV = Math.min(...values)
    const maxV = Math.max(...values)
    const range = maxV - minV || 1

    const padL = 72
    const padR = 12
    const padT = 12
    const padB = 28

    const chartW = w - padL - padR
    const chartH = h - padT - padB

    const scaleX = chartW / (history.length - 1)
    const scaleY = chartH / range

    const xOf = (i: number) => padL + i * scaleX
    const yOf = (v: number) => padT + chartH - (v - minV) * scaleY

    // Grid
    ctx.strokeStyle = '#2a2d3a'
    ctx.lineWidth = 1
    const gridCount = 4
    for (let i = 0; i <= gridCount; i++) {
      const val = minV + (range / gridCount) * i
      const y = yOf(val)
      ctx.beginPath()
      ctx.moveTo(padL, y)
      ctx.lineTo(w - padR, y)
      ctx.stroke()

      ctx.fillStyle = '#64748b'
      ctx.font = '10px JetBrains Mono, monospace'
      ctx.textAlign = 'right'
      ctx.fillText(formatCurrency(val, 0), padL - 4, y + 3)
    }

    // Time labels
    const labelStep = Math.max(1, Math.floor(history.length / 5))
    ctx.fillStyle = '#64748b'
    ctx.font = '10px JetBrains Mono, monospace'
    ctx.textAlign = 'center'
    for (let i = 0; i < history.length; i += labelStep) {
      const d = new Date(history[i].recorded_at)
      const label = d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false })
      ctx.fillText(label, xOf(i), h - 6)
    }

    // First vs last value color
    const isUp = values[values.length - 1] >= values[0]
    const lineColor = isUp ? '#22c55e' : '#ef4444'

    // Fill
    const gradient = ctx.createLinearGradient(0, padT, 0, padT + chartH)
    gradient.addColorStop(0, isUp ? 'rgba(34,197,94,0.25)' : 'rgba(239,68,68,0.25)')
    gradient.addColorStop(1, 'rgba(0,0,0,0)')

    ctx.beginPath()
    history.forEach((snap, i) => {
      const x = xOf(i)
      const y = yOf(snap.total_value)
      if (i === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    })
    ctx.lineTo(xOf(history.length - 1), padT + chartH)
    ctx.lineTo(xOf(0), padT + chartH)
    ctx.closePath()
    ctx.fillStyle = gradient
    ctx.fill()

    // Line
    ctx.strokeStyle = lineColor
    ctx.lineWidth = 2
    ctx.lineJoin = 'round'
    ctx.beginPath()
    history.forEach((snap, i) => {
      const x = xOf(i)
      const y = yOf(snap.total_value)
      if (i === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    })
    ctx.stroke()

    // Baseline reference line ($10,000)
    const baseline = 10000
    if (baseline >= minV && baseline <= maxV) {
      const y = yOf(baseline)
      ctx.strokeStyle = '#ecad0a'
      ctx.lineWidth = 1
      ctx.setLineDash([3, 3])
      ctx.beginPath()
      ctx.moveTo(padL, y)
      ctx.lineTo(w - padR, y)
      ctx.stroke()
      ctx.setLineDash([])
    }
  }, [history])

  useEffect(() => {
    drawChart()
  }, [drawChart])

  useEffect(() => {
    const observer = new ResizeObserver(() => drawChart())
    if (containerRef.current) observer.observe(containerRef.current)
    return () => observer.disconnect()
  }, [drawChart])

  const lastValue = history.length > 0 ? history[history.length - 1].total_value : null
  const firstValue = history.length > 0 ? history[0].total_value : null
  const change = lastValue !== null && firstValue !== null ? lastValue - firstValue : null

  return (
    <div className="flex flex-col h-full bg-bg-primary">
      <div className="px-3 py-2 border-b border-bg-border flex items-center gap-3 shrink-0">
        <span className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
          P&amp;L
        </span>
        {lastValue !== null && (
          <span className="font-terminal text-sm text-accent-yellow font-semibold">
            {formatCurrency(lastValue)}
          </span>
        )}
        {change !== null && (
          <span
            className={`font-terminal text-xs ${change >= 0 ? 'text-price-up' : 'text-price-down'}`}
          >
            {change >= 0 ? '+' : ''}{formatCurrency(change)}
          </span>
        )}
      </div>
      <div ref={containerRef} className="flex-1 relative min-h-0">
        <canvas ref={canvasRef} className="absolute inset-0" />
      </div>
    </div>
  )
}
