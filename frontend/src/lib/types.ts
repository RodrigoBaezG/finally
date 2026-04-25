export interface PriceUpdate {
  ticker: string
  price: number
  previous_price: number
  session_start_price: number
  timestamp: number
  change: number
  change_percent: number
  session_change_percent: number
  direction: 'up' | 'down' | 'flat'
}

export type PriceMap = Record<string, PriceUpdate>

export interface SparklinePoint {
  time: number
  price: number
}

export type SparklineData = SparklinePoint[]

export interface WatchlistItem {
  ticker: string
  price: number
  previous_price: number
  session_start_price: number
  session_change_percent: number
  direction: 'up' | 'down' | 'flat'
}

export interface Position {
  ticker: string
  quantity: number
  avg_cost: number
  current_price: number
  unrealized_pnl: number
  pnl_percent: number
}

export interface Portfolio {
  cash_balance: number
  total_value: number
  total_unrealized_pnl: number
  positions: Position[]
}

export interface TradeRecord {
  ticker: string
  side: 'buy' | 'sell'
  quantity: number
  price: number
  executed_at: string
}

export interface TradeResponse {
  success: boolean
  message: string
  trade?: TradeRecord
  portfolio?: Portfolio
}

export interface TradeRequest {
  ticker: string
  quantity: number
  side: 'buy' | 'sell'
}

export interface PortfolioSnapshot {
  recorded_at: string
  total_value: number
}

export interface ChatTradeAction {
  ticker: string
  side: 'buy' | 'sell'
  quantity: number
  price?: number
  status?: string
  error?: string
}

export interface ChatWatchlistAction {
  ticker: string
  action: 'add' | 'remove'
  status?: string
  error?: string
}

export interface ChatRequest {
  message: string
}

export interface ChatResponse {
  message: string
  trades?: ChatTradeAction[]
  watchlist_changes?: ChatWatchlistAction[]
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  trades?: ChatTradeAction[]
  watchlist_changes?: ChatWatchlistAction[]
  created_at: string
}
