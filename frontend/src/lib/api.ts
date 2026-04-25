import type {
  ChatRequest,
  ChatResponse,
  Portfolio,
  PortfolioSnapshot,
  TradeRequest,
  TradeResponse,
  WatchlistItem,
} from './types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  })

  if (!res.ok) {
    let detail = `Request failed (${res.status})`
    try {
      const data = await res.json()
      if (data?.detail) {
        detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
      } else if (data?.message) {
        detail = data.message
      }
    } catch {
      // ignore parse errors
    }
    throw new Error(detail)
  }

  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export const api = {
  getPortfolio(): Promise<Portfolio> {
    return request<Portfolio>('/api/portfolio')
  },

  getPortfolioHistory(): Promise<PortfolioSnapshot[]> {
    return request<PortfolioSnapshot[]>('/api/portfolio/history')
  },

  async trade(body: TradeRequest): Promise<TradeResponse> {
    try {
      return await request<TradeResponse>('/api/portfolio/trade', {
        method: 'POST',
        body: JSON.stringify(body),
      })
    } catch (err) {
      return {
        success: false,
        message: err instanceof Error ? err.message : 'Trade failed',
      }
    }
  },

  getWatchlist(): Promise<WatchlistItem[]> {
    return request<WatchlistItem[]>('/api/watchlist')
  },

  addTicker(ticker: string): Promise<WatchlistItem> {
    return request<WatchlistItem>('/api/watchlist', {
      method: 'POST',
      body: JSON.stringify({ ticker }),
    })
  },

  async removeTicker(ticker: string): Promise<void> {
    await request<void>(`/api/watchlist/${encodeURIComponent(ticker)}`, {
      method: 'DELETE',
    })
  },

  chat(body: ChatRequest): Promise<ChatResponse> {
    return request<ChatResponse>('/api/chat', {
      method: 'POST',
      body: JSON.stringify(body),
    })
  },
}
