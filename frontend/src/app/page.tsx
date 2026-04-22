'use client'

import { useEffect, useState, useCallback, useRef } from 'react'
import { Header } from '@/components/Header'
import { WatchlistPanel } from '@/components/WatchlistPanel'
import { MainChart } from '@/components/MainChart'
import { PortfolioHeatmap } from '@/components/PortfolioHeatmap'
import { PnLChart } from '@/components/PnLChart'
import { PositionsTable } from '@/components/PositionsTable'
import { TradeBar } from '@/components/TradeBar'
import { ChatPanel } from '@/components/ChatPanel'
import { usePriceStream } from '@/hooks/usePriceStream'
import { usePortfolio } from '@/hooks/usePortfolio'
import { api } from '@/lib/api'
import type { WatchlistItem, PortfolioSnapshot } from '@/lib/types'

export default function TradingWorkstation() {
  const { prices, sparklines, status, flashMap } = usePriceStream()
  const { portfolio, refresh: refreshPortfolio, computeLiveValue } = usePortfolio()

  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([])
  const [history, setHistory] = useState<PortfolioSnapshot[]>([])
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null)
  const [chatOpen, setChatOpen] = useState(true)

  const liveTotal = computeLiveValue(prices)

  // Load initial data
  const loadWatchlist = useCallback(async () => {
    try {
      const wl = await api.getWatchlist()
      setWatchlist(wl)
      // Auto-select first ticker if none selected
      if (wl.length > 0 && !selectedTicker) {
        setSelectedTicker(wl[0].ticker)
      }
    } catch {
      // ignore on initial load
    }
  }, [selectedTicker])

  const loadHistory = useCallback(async () => {
    try {
      const h = await api.getPortfolioHistory()
      setHistory(h)
    } catch {
      // ignore
    }
  }, [])

  useEffect(() => {
    refreshPortfolio()
    loadWatchlist()
    loadHistory()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Poll history periodically (every 30s to match backend snapshot interval)
  const historyIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  useEffect(() => {
    historyIntervalRef.current = setInterval(loadHistory, 30_000)
    return () => {
      if (historyIntervalRef.current) clearInterval(historyIntervalRef.current)
    }
  }, [loadHistory])

  const handleTradeComplete = useCallback(() => {
    refreshPortfolio()
    loadHistory()
  }, [refreshPortfolio, loadHistory])

  const handlePortfolioChange = useCallback(() => {
    refreshPortfolio()
    loadHistory()
  }, [refreshPortfolio, loadHistory])

  const handleWatchlistChange = useCallback(() => {
    loadWatchlist()
  }, [loadWatchlist])

  const selectedSparkline = selectedTicker ? (sparklines[selectedTicker] ?? []) : []
  const selectedPrice = selectedTicker ? (prices[selectedTicker]?.price ?? null) : null

  const cashBalance = portfolio?.cash_balance ?? 0
  const displayTotal = liveTotal > 0 ? liveTotal : (portfolio?.total_value ?? 0)

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-bg-primary">
      {/* Header */}
      <Header
        status={status}
        portfolioTotal={displayTotal}
        cashBalance={cashBalance}
      />

      {/* Main content area */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* Left: Watchlist */}
        <div className="w-[220px] shrink-0 flex flex-col min-h-0">
          <WatchlistPanel
            watchlist={watchlist}
            prices={prices}
            sparklines={sparklines}
            flashMap={flashMap}
            selectedTicker={selectedTicker}
            onSelectTicker={setSelectedTicker}
            onWatchlistChange={handleWatchlistChange}
          />
        </div>

        {/* Center: charts + table */}
        <div className="flex flex-1 flex-col min-h-0 min-w-0">
          {/* Top row: main chart + heatmap */}
          <div className="flex flex-1 min-h-0 border-b border-bg-border">
            {/* Main chart */}
            <div className="flex-1 min-w-0 border-r border-bg-border">
              <MainChart
                ticker={selectedTicker}
                data={selectedSparkline}
                currentPrice={selectedPrice}
              />
            </div>
            {/* Portfolio heatmap */}
            <div className="w-[260px] shrink-0">
              <PortfolioHeatmap
                positions={portfolio?.positions ?? []}
                prices={prices}
                totalValue={displayTotal}
              />
            </div>
          </div>

          {/* Bottom row: P&L chart + positions table */}
          <div className="flex h-[200px] shrink-0 border-b border-bg-border">
            {/* P&L chart */}
            <div className="w-[320px] shrink-0 border-r border-bg-border">
              <PnLChart history={history} />
            </div>
            {/* Positions table */}
            <div className="flex-1 min-w-0">
              <PositionsTable
                positions={portfolio?.positions ?? []}
                prices={prices}
              />
            </div>
          </div>

          {/* Trade bar */}
          <TradeBar
            prices={prices}
            cashBalance={cashBalance}
            onTradeComplete={handleTradeComplete}
          />
        </div>

        {/* Right: AI Chat */}
        <div
          className={`shrink-0 flex flex-col min-h-0 transition-all duration-200 ${
            chatOpen ? 'w-[300px]' : 'w-0 overflow-hidden'
          }`}
        >
          <ChatPanel
            onPortfolioChange={handlePortfolioChange}
            onWatchlistChange={handleWatchlistChange}
            isCollapsed={!chatOpen}
            onToggle={() => setChatOpen(prev => !prev)}
          />
        </div>
      </div>

      {/* Chat toggle button when collapsed */}
      {!chatOpen && (
        <button
          onClick={() => setChatOpen(true)}
          className="fixed bottom-16 right-0 bg-accent-purple hover:bg-purple-700 text-white text-xs px-3 py-2 rounded-l font-semibold transition-colors z-20"
          aria-label="Open AI Chat"
        >
          AI
        </button>
      )}
    </div>
  )
}
