'use client'

import { useState, useRef, useEffect, useCallback } from 'react'
import { api } from '@/lib/api'
import type { ChatMessage, ChatTradeAction, ChatWatchlistAction } from '@/lib/types'
import { generateId } from '@/lib/utils'

interface ChatPanelProps {
  onPortfolioChange: () => void
  onWatchlistChange: () => void
  isCollapsed: boolean
  onToggle: () => void
}

function TradeConfirmation({ trades }: { trades: ChatTradeAction[] }) {
  if (trades.length === 0) return null
  return (
    <div className="mt-2 space-y-1">
      {trades.map((t, i) => (
        <div
          key={i}
          className={`text-xs font-terminal px-2 py-1 rounded ${
            t.side === 'buy'
              ? 'bg-green-900/40 text-green-300 border border-green-800'
              : 'bg-red-900/40 text-red-300 border border-red-800'
          }`}
        >
          {t.side === 'buy' ? 'Bought' : 'Sold'} {t.quantity}x {t.ticker}
        </div>
      ))}
    </div>
  )
}

function WatchlistConfirmation({ changes }: { changes: ChatWatchlistAction[] }) {
  if (changes.length === 0) return null
  return (
    <div className="mt-2 space-y-1">
      {changes.map((c, i) => (
        <div
          key={i}
          className="text-xs font-terminal px-2 py-1 rounded bg-blue-900/40 text-blue-300 border border-blue-800"
        >
          {c.action === 'add' ? 'Added' : 'Removed'} {c.ticker} from watchlist
        </div>
      ))}
    </div>
  )
}

export function ChatPanel({
  onPortfolioChange,
  onWatchlistChange,
  isCollapsed,
  onToggle,
}: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages, scrollToBottom])

  const sendMessage = useCallback(async () => {
    const text = input.trim()
    if (!text || loading) return

    const userMsg: ChatMessage = {
      id: generateId(),
      role: 'user',
      content: text,
      created_at: new Date().toISOString(),
    }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)

    try {
      const response = await api.chat({ message: text })

      const assistantMsg: ChatMessage = {
        id: generateId(),
        role: 'assistant',
        content: response.message,
        trades: response.trades,
        watchlist_changes: response.watchlist_changes,
        created_at: new Date().toISOString(),
      }
      setMessages(prev => [...prev, assistantMsg])

      // If the AI executed trades or watchlist changes, refresh data
      if (response.trades && response.trades.length > 0) {
        onPortfolioChange()
      }
      if (response.watchlist_changes && response.watchlist_changes.length > 0) {
        onWatchlistChange()
      }
    } catch (err) {
      const errMsg: ChatMessage = {
        id: generateId(),
        role: 'assistant',
        content: `Error: ${err instanceof Error ? err.message : 'Failed to get response'}`,
        created_at: new Date().toISOString(),
      }
      setMessages(prev => [...prev, errMsg])
    } finally {
      setLoading(false)
    }
  }, [input, loading, onPortfolioChange, onWatchlistChange])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  if (isCollapsed) {
    return (
      <button
        onClick={onToggle}
        className="fixed bottom-16 right-0 bg-accent-purple hover:bg-purple-700 text-white text-xs px-3 py-2 rounded-l font-semibold transition-colors z-20"
        aria-label="Open AI Chat"
      >
        AI
      </button>
    )
  }

  return (
    <div className="flex flex-col h-full bg-bg-secondary border-l border-bg-border">
      {/* Chat header */}
      <div className="px-3 py-2 border-b border-bg-border flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-accent-purple" />
          <span className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
            FinAlly AI
          </span>
        </div>
        <button
          onClick={onToggle}
          className="text-text-muted hover:text-text-primary text-xs transition-colors"
          aria-label="Collapse chat"
        >
          →
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto min-h-0 p-3 space-y-3">
        {messages.length === 0 && (
          <div className="text-text-muted text-xs text-center py-4">
            <div className="font-semibold text-text-secondary mb-1">FinAlly AI</div>
            <div>Ask about your portfolio, get analysis, or have me execute trades.</div>
          </div>
        )}
        {messages.map(msg => (
          <div
            key={msg.id}
            data-testid={`chat-message-${msg.role}`}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[90%] rounded px-3 py-2 text-xs leading-relaxed ${
                msg.role === 'user'
                  ? 'bg-accent-purple/20 border border-accent-purple/30 text-text-primary'
                  : 'bg-bg-elevated border border-bg-border text-text-primary'
              }`}
            >
              {msg.role === 'assistant' && (
                <div className="text-accent-purple text-[10px] font-semibold mb-1 uppercase tracking-wider">
                  FinAlly
                </div>
              )}
              <div className="whitespace-pre-wrap">{msg.content}</div>
              {msg.trades && msg.trades.length > 0 && (
                <TradeConfirmation trades={msg.trades} />
              )}
              {msg.watchlist_changes && msg.watchlist_changes.length > 0 && (
                <WatchlistConfirmation changes={msg.watchlist_changes} />
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-bg-elevated border border-bg-border rounded px-3 py-2">
              <div className="flex items-center gap-1.5">
                <div className="w-1.5 h-1.5 rounded-full bg-accent-purple animate-bounce" style={{ animationDelay: '0ms' }} />
                <div className="w-1.5 h-1.5 rounded-full bg-accent-purple animate-bounce" style={{ animationDelay: '150ms' }} />
                <div className="w-1.5 h-1.5 rounded-full bg-accent-purple animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="px-3 py-2 border-t border-bg-border shrink-0">
        <div className="flex gap-2">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask FinAlly..."
            disabled={loading}
            className="flex-1 bg-bg-primary border border-bg-border rounded px-2 py-1.5 text-xs text-text-primary placeholder-text-muted focus:outline-none focus:border-accent-purple disabled:opacity-50"
            data-testid="chat-input"
          />
          <button
            onClick={sendMessage}
            disabled={loading || !input.trim()}
            className="bg-accent-purple hover:bg-purple-700 disabled:opacity-40 text-white text-xs px-3 py-1.5 rounded font-semibold transition-colors"
            data-testid="chat-send"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  )
}
