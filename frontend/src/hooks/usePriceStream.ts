'use client'

import { useEffect, useRef, useCallback, useState } from 'react'
import type { PriceMap, SparklineData } from '@/lib/types'

export type ConnectionStatus = 'connected' | 'disconnected'

export interface PriceStreamState {
  prices: PriceMap
  sparklines: Record<string, SparklineData>
  status: ConnectionStatus
  flashMap: Record<string, 'up' | 'down' | null>
}

interface UsePriceStreamOptions {
  onPriceUpdate?: (updates: PriceMap) => void
}

const SSE_URL = '/api/stream/prices'
const MAX_SPARKLINE_POINTS = 120  // ~60 seconds of data at 500ms intervals

export function usePriceStream(options: UsePriceStreamOptions = {}): PriceStreamState {
  const [prices, setPrices] = useState<PriceMap>({})
  const [sparklines, setSparklines] = useState<Record<string, SparklineData>>({})
  const [status, setStatus] = useState<ConnectionStatus>('disconnected')
  const [flashMap, setFlashMap] = useState<Record<string, 'up' | 'down' | null>>({})

  const onPriceUpdateRef = useRef(options.onPriceUpdate)
  onPriceUpdateRef.current = options.onPriceUpdate

  const flashTimersRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({})

  const triggerFlash = useCallback((ticker: string, direction: 'up' | 'down') => {
    // Clear any existing flash timer for this ticker
    if (flashTimersRef.current[ticker]) {
      clearTimeout(flashTimersRef.current[ticker])
    }

    setFlashMap(prev => ({ ...prev, [ticker]: direction }))

    flashTimersRef.current[ticker] = setTimeout(() => {
      setFlashMap(prev => ({ ...prev, [ticker]: null }))
    }, 500)
  }, [])

  useEffect(() => {
    let es: EventSource | null = null

    function connect() {
      es = new EventSource(SSE_URL)

      es.onopen = () => {
        setStatus('connected')
      }

      es.onerror = () => {
        setStatus('disconnected')
        // EventSource will auto-reconnect; we just update status
      }

      es.onmessage = (event: MessageEvent<string>) => {
        let updates: PriceMap
        try {
          updates = JSON.parse(event.data) as PriceMap
        } catch {
          return
        }

        // Trigger flash and update sparklines
        const newFlashes: Record<string, 'up' | 'down'> = {}

        setPrices(prev => {
          const next = { ...prev }
          for (const [ticker, update] of Object.entries(updates)) {
            const prevUpdate = prev[ticker]
            if (prevUpdate !== undefined && update.price !== prevUpdate.price) {
              if (update.direction === 'up' || update.direction === 'down') {
                newFlashes[ticker] = update.direction
              }
            }
            next[ticker] = update
          }
          return next
        })

        // Update sparklines
        setSparklines(prev => {
          const next = { ...prev }
          for (const [ticker, update] of Object.entries(updates)) {
            const existing = prev[ticker] ?? []
            const point = { time: update.timestamp, price: update.price }
            const updated = [...existing, point]
            next[ticker] = updated.length > MAX_SPARKLINE_POINTS
              ? updated.slice(updated.length - MAX_SPARKLINE_POINTS)
              : updated
          }
          return next
        })

        // Apply flashes
        for (const [ticker, dir] of Object.entries(newFlashes)) {
          triggerFlash(ticker, dir)
        }

        onPriceUpdateRef.current?.(updates)
      }
    }

    connect()

    const timerMap = flashTimersRef
    return () => {
      es?.close()
      // Clear all flash timers
      for (const timer of Object.values(timerMap.current)) {
        clearTimeout(timer)
      }
    }
  }, [triggerFlash])

  return { prices, sparklines, status, flashMap }
}
