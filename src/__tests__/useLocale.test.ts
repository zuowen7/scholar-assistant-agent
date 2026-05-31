import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { useLocale, _resetLocale } from '../composables/useLocale'

describe('useLocale', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.stubGlobal('navigator', { language: 'zh-CN' })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('defaults to zh-CN when no stored preference and system is Chinese', () => {
    _resetLocale()
    const { currentLocale } = useLocale()
    expect(currentLocale.value).toBe('zh-CN')
  })

  it('restores locale from localStorage', () => {
    localStorage.setItem('lang', 'en-US')
    _resetLocale()
    const { currentLocale } = useLocale()
    expect(currentLocale.value).toBe('en-US')
  })

  it('switches locale and persists to localStorage', () => {
    _resetLocale()
    const { currentLocale, setLocale } = useLocale()
    setLocale('en-US')
    expect(currentLocale.value).toBe('en-US')
    expect(localStorage.getItem('lang')).toBe('en-US')
  })

  it('sets document.documentElement.lang on switch', () => {
    _resetLocale()
    const { setLocale } = useLocale()
    setLocale('en-US')
    expect(document.documentElement.lang).toBe('en-US')
  })

  it('detects English system language and auto-selects en-US', () => {
    vi.stubGlobal('navigator', { language: 'en-US' })
    localStorage.clear()
    _resetLocale()
    const { currentLocale } = useLocale()
    expect(currentLocale.value).toBe('en-US')
  })
})
