import { describe, it, expect } from 'vitest'
import { formatCurrency, formatPercent, formatNumber, generateId } from '@/lib/utils'

describe('formatCurrency', () => {
  it('formats positive values', () => {
    expect(formatCurrency(1234.56)).toBe('$1,234.56')
  })

  it('formats negative values', () => {
    expect(formatCurrency(-500.5)).toBe('-$500.50')
  })

  it('formats zero', () => {
    expect(formatCurrency(0)).toBe('$0.00')
  })

  it('formats with custom decimals', () => {
    expect(formatCurrency(10000, 0)).toBe('$10,000')
  })
})

describe('formatPercent', () => {
  it('formats positive percent with + sign', () => {
    expect(formatPercent(2.5)).toBe('+2.50%')
  })

  it('formats negative percent without + sign', () => {
    expect(formatPercent(-1.23)).toBe('-1.23%')
  })

  it('formats zero with + sign', () => {
    expect(formatPercent(0)).toBe('+0.00%')
  })
})

describe('formatNumber', () => {
  it('formats large numbers with commas', () => {
    expect(formatNumber(1234567.89)).toBe('1,234,567.89')
  })
})

describe('generateId', () => {
  it('returns a non-empty string', () => {
    const id = generateId()
    expect(typeof id).toBe('string')
    expect(id.length).toBeGreaterThan(0)
  })

  it('returns unique ids', () => {
    const ids = new Set(Array.from({ length: 100 }, () => generateId()))
    expect(ids.size).toBe(100)
  })
})
