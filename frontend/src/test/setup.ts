import '@testing-library/jest-dom'
import { vi } from 'vitest'

// Mock EventSource globally (not available in jsdom)
class MockEventSource {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSED = 2

  url: string
  readyState = MockEventSource.CONNECTING
  onopen: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null

  constructor(url: string) {
    this.url = url
  }

  close() {
    this.readyState = MockEventSource.CLOSED
  }

  // Test helpers
  simulateOpen() {
    this.readyState = MockEventSource.OPEN
    this.onopen?.(new Event('open'))
  }

  simulateMessage(data: unknown) {
    this.onmessage?.(
      new MessageEvent('message', { data: JSON.stringify(data) })
    )
  }

  simulateError() {
    this.readyState = MockEventSource.CLOSED
    this.onerror?.(new Event('error'))
  }
}

vi.stubGlobal('EventSource', MockEventSource)

// Mock ResizeObserver
vi.stubGlobal('ResizeObserver', class MockResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
})

// Mock canvas getContext
HTMLCanvasElement.prototype.getContext = vi.fn(() => null)

// Mock scrollIntoView (not available in jsdom)
window.HTMLElement.prototype.scrollIntoView = vi.fn()
