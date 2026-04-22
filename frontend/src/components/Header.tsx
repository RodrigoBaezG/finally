'use client'

import type { ConnectionStatus } from '@/hooks/usePriceStream'
import { formatCurrency } from '@/lib/utils'

interface HeaderProps {
  status: ConnectionStatus
  portfolioTotal: number
  cashBalance: number
}

export function Header({ status, portfolioTotal, cashBalance }: HeaderProps) {
  const connected = status === 'connected'

  return (
    <header className="flex items-center justify-between px-4 py-2 border-b border-bg-border bg-bg-secondary shrink-0">
      {/* Brand */}
      <div className="flex items-center gap-3">
        <span className="text-accent-yellow font-bold text-lg tracking-widest font-mono">
          FIN<span className="text-accent-blue">ALLY</span>
        </span>
        <span className="text-text-muted text-xs uppercase tracking-wider hidden sm:block">
          AI Trading Workstation
        </span>
      </div>

      {/* Center: portfolio value */}
      <div className="flex items-center gap-6">
        <div className="text-center">
          <div className="text-text-muted text-xs uppercase tracking-wider">Portfolio</div>
          <div
            className="font-terminal text-accent-yellow font-semibold text-base"
            data-testid="portfolio-total"
          >
            {formatCurrency(portfolioTotal)}
          </div>
        </div>
        <div className="text-center">
          <div className="text-text-muted text-xs uppercase tracking-wider">Cash</div>
          <div
            className="font-terminal text-text-primary font-medium text-base"
            data-testid="cash-balance"
          >
            {formatCurrency(cashBalance)}
          </div>
        </div>
      </div>

      {/* Right: connection status */}
      <div className="flex items-center gap-2">
        <div
          className={`w-2 h-2 rounded-full ${connected ? 'bg-price-up' : 'bg-price-down'}`}
          style={{
            boxShadow: connected
              ? '0 0 6px rgba(34,197,94,0.7)'
              : '0 0 6px rgba(239,68,68,0.7)',
          }}
          data-testid="connection-status"
          data-status={connected ? 'connected' : 'disconnected'}
        />
        <span className="text-xs text-text-muted hidden sm:block">
          {connected ? 'LIVE' : 'OFFLINE'}
        </span>
      </div>
    </header>
  )
}
