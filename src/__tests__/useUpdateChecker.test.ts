import { describe, it, expect, vi, beforeEach } from 'vitest'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

vi.mock('../composables/useToast', () => {
  const toasts: any[] = []
  const push = (level: string) => vi.fn((msg: string) => toasts.push({ level, message: msg }))
  return {
    useToast: () => ({
      success: push('success'),
      info: push('info'),
      warn: push('warn'),
      danger: push('danger'),
      toasts,
    }),
    toasts: { value: toasts },
  }
})

const localStorageStore: Record<string, string> = {}
vi.stubGlobal('localStorage', {
  getItem: vi.fn((k: string) => localStorageStore[k] ?? null),
  setItem: vi.fn((k: string, v: string) => { localStorageStore[k] = v }),
  removeItem: vi.fn((k: string) => { delete localStorageStore[k] }),
  clear: vi.fn(() => Object.keys(localStorageStore).forEach(k => delete localStorageStore[k])),
})

// ---------------------------------------------------------------------------
// Import after mocks
// ---------------------------------------------------------------------------

import { compareVersions, checkForUpdate } from '../composables/useUpdateChecker'

// ---------------------------------------------------------------------------
// compareVersions
// ---------------------------------------------------------------------------

describe('compareVersions', () => {
  it('remote patch newer → -1', () => {
    expect(compareVersions('0.3.1', '0.3.2')).toBe(-1)
  })

  it('identical → 0', () => {
    expect(compareVersions('0.3.2', '0.3.2')).toBe(0)
  })

  it('local newer → 1', () => {
    expect(compareVersions('0.4.0', '0.3.2')).toBe(1)
  })

  it('major version diff', () => {
    expect(compareVersions('1.0.0', '0.9.9')).toBe(1)
  })

  it('minor version diff', () => {
    expect(compareVersions('0.3.2', '0.2.9')).toBe(1)
  })

  it('strips v prefix from remote', () => {
    expect(compareVersions('0.3.1', 'v0.3.2')).toBe(-1)
  })

  it('both have v prefix', () => {
    expect(compareVersions('v0.3.2', 'v0.3.2')).toBe(0)
  })
})

// ---------------------------------------------------------------------------
// checkForUpdate
// ---------------------------------------------------------------------------

describe('checkForUpdate', () => {
  beforeEach(() => {
    mockFetch.mockReset()
    localStorage.clear()
  })

  async function mockHealthAndGithub(healthVersion: string, githubTag: string) {
    mockFetch
      .mockImplementationOnce(() =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ status: 'ok', version: healthVersion }),
        } as Response)
      )
      .mockImplementationOnce(() =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ tag_name: githubTag, html_url: 'https://github.com/example/releases/tag/' + githubTag }),
        } as Response)
      )
  }

  it('newer remote → pushes info toast', async () => {
    await mockHealthAndGithub('0.3.1', 'v0.3.2')
    await checkForUpdate()
    expect(mockFetch).toHaveBeenCalledTimes(2)
  })

  it('same version → no toast', async () => {
    await mockHealthAndGithub('0.3.2', 'v0.3.2')
    await checkForUpdate()
    expect(mockFetch).toHaveBeenCalledTimes(2)
  })

  it('older remote → no toast', async () => {
    await mockHealthAndGithub('0.4.0', 'v0.3.2')
    await checkForUpdate()
    expect(mockFetch).toHaveBeenCalledTimes(2)
  })

  it('network error on health check → silent', async () => {
    mockFetch.mockRejectedValueOnce(new Error('Network error'))
    await expect(checkForUpdate()).resolves.toBeUndefined()
  })

  it('network error on github API → silent', async () => {
    mockFetch
      .mockImplementationOnce(() =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ status: 'ok', version: '0.3.1' }),
        } as Response)
      )
      .mockRejectedValueOnce(new Error('Network error'))
    await expect(checkForUpdate()).resolves.toBeUndefined()
  })

  it('same version already notified → no duplicate toast', async () => {
    await mockHealthAndGithub('0.3.1', 'v0.3.2')
    await checkForUpdate()

    // Second check — fetches happen (lightweight) but no toast for same version
    await mockHealthAndGithub('0.3.1', 'v0.3.2')
    await checkForUpdate()
    expect(mockFetch).toHaveBeenCalledTimes(4) // 2 calls × 2 checks
  })

  it('newer version after previous notification → notifies again', async () => {
    await mockHealthAndGithub('0.3.1', 'v0.3.2')
    await checkForUpdate()

    // New version released
    mockFetch.mockReset()
    await mockHealthAndGithub('0.3.1', 'v0.3.3')
    await checkForUpdate()
    expect(mockFetch).toHaveBeenCalledTimes(2)
  })

  it('malformed github response → silent', async () => {
    mockFetch
      .mockImplementationOnce(() =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ status: 'ok', version: '0.3.1' }),
        } as Response)
      )
      .mockImplementationOnce(() =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve({}),
        } as Response)
      )
    await expect(checkForUpdate()).resolves.toBeUndefined()
  })

  it('github returns non-ok status → silent', async () => {
    mockFetch
      .mockImplementationOnce(() =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ status: 'ok', version: '0.3.1' }),
        } as Response)
      )
      .mockImplementationOnce(() =>
        Promise.resolve({ ok: false, status: 403 } as Response)
      )
    await expect(checkForUpdate()).resolves.toBeUndefined()
  })
})
