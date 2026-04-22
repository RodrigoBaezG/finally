'use client'

import { useEffect, useRef } from 'react'
import type { SparklineData } from '@/lib/types'

interface SparklineProps {
  data: SparklineData
  width?: number
  height?: number
  color?: string
}

export function Sparkline({
  data,
  width = 80,
  height = 28,
  color = '#209dd7',
}: SparklineProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    // High-DPI support
    const dpr = window.devicePixelRatio ?? 1
    canvas.width = width * dpr
    canvas.height = height * dpr
    ctx.scale(dpr, dpr)

    ctx.clearRect(0, 0, width, height)

    if (data.length < 2) {
      // Draw flat line
      ctx.strokeStyle = color
      ctx.lineWidth = 1
      ctx.beginPath()
      ctx.moveTo(0, height / 2)
      ctx.lineTo(width, height / 2)
      ctx.stroke()
      return
    }

    const prices = data.map(d => d.price)
    const minP = Math.min(...prices)
    const maxP = Math.max(...prices)
    const range = maxP - minP || 1

    const pad = 2
    const scaleX = (width - pad * 2) / (data.length - 1)
    const scaleY = (height - pad * 2) / range

    // Determine color based on start vs end
    const startPrice = data[0].price
    const endPrice = data[data.length - 1].price
    const lineColor = endPrice >= startPrice ? '#22c55e' : '#ef4444'

    ctx.strokeStyle = lineColor
    ctx.lineWidth = 1.5
    ctx.lineJoin = 'round'
    ctx.lineCap = 'round'
    ctx.beginPath()

    data.forEach((point, i) => {
      const x = pad + i * scaleX
      const y = height - pad - (point.price - minP) * scaleY
      if (i === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    })
    ctx.stroke()

    // Fill gradient below line
    const lastX = pad + (data.length - 1) * scaleX
    const lastY = height - pad - (data[data.length - 1].price - minP) * scaleY
    ctx.lineTo(lastX, height - pad)
    ctx.lineTo(pad, height - pad)

    const gradient = ctx.createLinearGradient(0, 0, 0, height)
    const alpha = endPrice >= startPrice ? 'rgba(34,197,94,' : 'rgba(239,68,68,'
    gradient.addColorStop(0, `${alpha}0.15)`)
    gradient.addColorStop(1, `${alpha}0)`)

    ctx.fillStyle = gradient
    ctx.fill()

    void lastY // used in path
  }, [data, width, height, color])

  return (
    <canvas
      ref={canvasRef}
      style={{ width, height }}
      aria-hidden="true"
    />
  )
}
