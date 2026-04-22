import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { ChatPanel } from '@/components/ChatPanel'

vi.mock('@/lib/api', () => ({
  api: {
    chat: vi.fn(),
  },
}))

import { api } from '@/lib/api'

const defaultProps = {
  onPortfolioChange: vi.fn(),
  onWatchlistChange: vi.fn(),
  isCollapsed: false,
  onToggle: vi.fn(),
}

describe('ChatPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders chat input and send button', () => {
    render(<ChatPanel {...defaultProps} />)
    expect(screen.getByTestId('chat-input')).toBeInTheDocument()
    expect(screen.getByTestId('chat-send')).toBeInTheDocument()
  })

  it('send button is disabled when input is empty', () => {
    render(<ChatPanel {...defaultProps} />)
    expect(screen.getByTestId('chat-send')).toBeDisabled()
  })

  it('renders user message after sending', async () => {
    vi.mocked(api.chat).mockResolvedValueOnce({
      message: 'I can help with that!',
    })

    render(<ChatPanel {...defaultProps} />)

    fireEvent.change(screen.getByTestId('chat-input'), {
      target: { value: 'Show my portfolio' },
    })
    fireEvent.click(screen.getByTestId('chat-send'))

    await waitFor(() => {
      const userMessages = screen.getAllByTestId('chat-message-user')
      expect(userMessages[0]).toHaveTextContent('Show my portfolio')
    })
  })

  it('renders assistant response after API call', async () => {
    vi.mocked(api.chat).mockResolvedValueOnce({
      message: 'Your portfolio is looking great!',
    })

    render(<ChatPanel {...defaultProps} />)

    fireEvent.change(screen.getByTestId('chat-input'), {
      target: { value: 'How is my portfolio?' },
    })
    fireEvent.click(screen.getByTestId('chat-send'))

    await waitFor(() => {
      const assistantMessages = screen.getAllByTestId('chat-message-assistant')
      expect(assistantMessages[0]).toHaveTextContent('Your portfolio is looking great!')
    })
  })

  it('clears input after sending', async () => {
    vi.mocked(api.chat).mockResolvedValueOnce({ message: 'Done!' })

    render(<ChatPanel {...defaultProps} />)

    const input = screen.getByTestId('chat-input')
    fireEvent.change(input, { target: { value: 'Buy 10 AAPL' } })
    fireEvent.click(screen.getByTestId('chat-send'))

    await waitFor(() => {
      expect(input).toHaveValue('')
    })
  })

  it('calls onPortfolioChange when trades are executed', async () => {
    const onPortfolioChange = vi.fn()
    vi.mocked(api.chat).mockResolvedValueOnce({
      message: 'Bought 5 AAPL for you',
      trades: [{ ticker: 'AAPL', side: 'buy', quantity: 5 }],
    })

    render(<ChatPanel {...defaultProps} onPortfolioChange={onPortfolioChange} />)

    fireEvent.change(screen.getByTestId('chat-input'), {
      target: { value: 'Buy 5 AAPL' },
    })
    fireEvent.click(screen.getByTestId('chat-send'))

    await waitFor(() => {
      expect(onPortfolioChange).toHaveBeenCalled()
    })
  })

  it('calls onWatchlistChange when watchlist changes are made', async () => {
    const onWatchlistChange = vi.fn()
    vi.mocked(api.chat).mockResolvedValueOnce({
      message: 'Added TSLA to your watchlist',
      watchlist_changes: [{ ticker: 'TSLA', action: 'add' }],
    })

    render(<ChatPanel {...defaultProps} onWatchlistChange={onWatchlistChange} />)

    fireEvent.change(screen.getByTestId('chat-input'), {
      target: { value: 'Add TSLA to watchlist' },
    })
    fireEvent.click(screen.getByTestId('chat-send'))

    await waitFor(() => {
      expect(onWatchlistChange).toHaveBeenCalled()
    })
  })

  it('shows trade confirmations inline in assistant message', async () => {
    vi.mocked(api.chat).mockResolvedValueOnce({
      message: 'Done!',
      trades: [{ ticker: 'AAPL', side: 'buy', quantity: 10 }],
    })

    render(<ChatPanel {...defaultProps} />)
    fireEvent.change(screen.getByTestId('chat-input'), { target: { value: 'Buy 10 AAPL' } })
    fireEvent.click(screen.getByTestId('chat-send'))

    await waitFor(() => {
      expect(screen.getByText('Bought 10x AAPL')).toBeInTheDocument()
    })
  })

  it('shows error message on API failure', async () => {
    vi.mocked(api.chat).mockRejectedValueOnce(new Error('Network error'))

    render(<ChatPanel {...defaultProps} />)
    fireEvent.change(screen.getByTestId('chat-input'), { target: { value: 'Hello' } })
    fireEvent.click(screen.getByTestId('chat-send'))

    await waitFor(() => {
      const errorMsg = screen.getAllByTestId('chat-message-assistant')
      expect(errorMsg[0]).toHaveTextContent('Error: Network error')
    })
  })

  it('shows collapsed state button when isCollapsed=true', () => {
    render(<ChatPanel {...defaultProps} isCollapsed={true} />)
    expect(screen.getByLabelText('Open AI Chat')).toBeInTheDocument()
  })

  it('sends on Enter key press', async () => {
    vi.mocked(api.chat).mockResolvedValueOnce({ message: 'Hi!' })

    render(<ChatPanel {...defaultProps} />)
    const input = screen.getByTestId('chat-input')
    fireEvent.change(input, { target: { value: 'Hello' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    await waitFor(() => {
      expect(api.chat).toHaveBeenCalledWith({ message: 'Hello' })
    })
  })
})
