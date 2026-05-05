import { describe, it, expect } from 'vitest'
import { API_BASE } from '../utils/api'

describe('API_BASE', () => {
  it('is a string', () => {
    expect(typeof API_BASE).toBe('string')
  })

  it('does not end with a trailing slash', () => {
    expect(API_BASE.endsWith('/')).toBe(false)
  })

  it('starts with http or is empty (dev proxy mode)', () => {
    expect(API_BASE === '' || API_BASE.startsWith('http')).toBe(true)
  })
})
