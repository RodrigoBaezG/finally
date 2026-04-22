'use client'

import { useEffect, useRef, useCallback } from 'react'
import type { SparklineData } from '@/lib/types'
import { formatCurrency } from '@/lib/utils'

interface MainChartProps {
  ticker: string | null
  data: SparklineData
  currentPrice: number | null
}

export function MainChart({ ticker, data, currentPrice }: MainChartProps) {
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

    // Background
    ctx.fillStyle = '#0d1117'
    ctx.fillRect(0, 0, w, h)

    if (data.length < 2) {
      // Empty state
      ctx.fillStyle = '#64748b'
      ctx.font = '14px Inter, sans-serif'
      ctx.textAlign = 'center'
      ctx.fillText(
        ticker ? `Waiting for data on ${ticker}...` : 'Click a ticker to view chart',
        w / 2,
        h / 2
      )
      return
    }

    const prices = data.map(d => d.price)
    const minP = Math.min(...prices)
    const maxP = Math.max(...prices)
    const range = maxP - minP || 1

    const padL = 70
    const padR = 16
    const padT = 16
    const padB = 32

    const chartW = w - padL - padR
    const chartH = h - padT - padB

    const scaleX = chartW / (data.length - 1)
    const scaleY = chartH / range

    const xOf = (i: number) => padL + i * scaleX
    const yOf = (p: number) => padT + chartH - (p - minP) * scaleY

    // Grid lines
    const gridCount = 5
    ctx.strokeStyle = '#2a2d3a'
    ctx.lineWidth = 1
    for (let i = 0; i <= gridCount; i++) {
      const price = minP + (range / gridCount) * i
      const y = yOf(price)
      ctx.beginPath()
      ctx.moveTo(padL, y)
      ctx.lineTo(w - padR, y)
      ctx.stroke()

      // Price labels
      ctx.fillStyle = '#64748b'
      ctx.font = '10px JetBrains Mono, monospace'
      ctx.textAlign = 'right'
      ctx.fillText(formatCurrency(price), padL - 4, y + 3)
    }

    // Time labels (every ~20% across x)
    const labelStep = Math.max(1, Math.floor(data.length / 5))
    ctx.fillStyle = '#64748b'
    ctx.font = '10px JetBrains Mono, monospace'
    ctx.textAlign = 'center'
    for (let i = 0; i < data.length; i += labelStep) {
      const d = new Date(data[i].time * 1000)
      const label = d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false })
      ctx.fillText(label, xOf(i), h - 6)
    }

    // Line color based on start vs end price
    const isUp = data[data.length - 1].price >= data[0].price
    const lineColor = isUp ? '#22c55e' : '#ef4444'

    // Fill gradient
    const gradient = ctx.createLinearGradient(0, padT, 0, padT + chartH)
    gradient.addColorStop(0, isUp ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)')
    gradient.addColorStop(1, 'rgba(0,0,0,0)')

    ctx.beginPath()
    data.forEach((point, i) => {
      const x = xOf(i)
      const y = yOf(point.price)
      if (i === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    })
    ctx.lineTo(xOf(data.length - 1), padT + chartH)
    ctx.lineTo(xOf(0), padT + chartH)
    ctx.closePath()
    ctx.fillStyle = gradient
    ctx.fill()

    // Price line
    ctx.strokeStyle = lineColor
    ctx.lineWidth = 2
    ctx.lineJoin = 'round'
    ctx.beginPath()
    data.forEach((point, i) => {
      const x = xOf(i)
      const y = yOf(point.price)
      if (i === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    })
    ctx.stroke()

    // Current price crosshair
    if (currentPrice !== null) {
      const y = yOf(currentPrice)
      ctx.strokeStyle = '#ecad0a'
      ctx.lineWidth = 1
      ctx.setLineDash([4, 4])
      ctx.beginPath()
      ctx.moveTo(padL, y)
      ctx.lineTo(w - padR, y)
      ctx.stroke()
      ctx.setLineDash([])

      // Price tag
      ctx.fillStyle = '#ecad0a'
      ctx.fillRect(w - padR + 2, y - 8, padR + 6, 16)
      ctx.fillStyle = '#0d1117'
      ctx.font = 'bold 9px JetBrains Mono, monospace'
      ctx.textAlign = 'left'
      ctx.fillText(currentPrice.toFixed(2), w - padR + 4, y + 3)
    }
  }, [data, ticker, currentPrice])

  useEffect(() => {
    drawChart()
  }, [drawChart])

  // Redraw on resize
  useEffect(() => {
    const observer = new ResizeObserver(() => drawChart())
    if (containerRef.current) observer.observe(containerRef.current)
    return () => observer.disconnect()
  }, [drawChart])

  return (
    <div className="flex flex-col h-full bg-bg-primary">
      <div className="px-3 py-2 border-b border-bg-border flex items-center gap-3 shrink-0">
        <span className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
          {ticker ?? 'Chart'}
        </span>
        {ticker && currentPrice !== null && (
          <>
            <span className="font-terminal text-accent-yellow text-sm font-semibold">
              {formatCurrency(currentPrice)}
            </span>
            <span className="text-text-muted text-xs">price chart</span>
          </>
        )}
      </div>
      <div ref={containerRef} className="flex-1 relative min-h-0">
        <canvas ref={canvasRef} className="absolute inset-0" />
      </div>
    </div>
  )
}
