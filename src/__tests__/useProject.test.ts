import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// Mock fetch globally
const mockFetch = vi.fn()
globalThis.fetch = mockFetch

vi.mock('../utils/api', () => ({
  API_BASE: '',
}))

// Mock useFileTree (openProject/closeProject import it dynamically)
vi.mock('../composables/useFileTree', () => ({
  useFileTree: () => ({
    openFolder: vi.fn().mockResolvedValue(undefined),
    rootDir: { value: null },
    files: { value: [] },
  }),
}))

// Reset module state between tests
import { currentProject, recentProjects, projectLoading } from '../composables/useProject'

describe('useProject', () => {
  beforeEach(() => {
    currentProject.value = null
    recentProjects.value = []
    projectLoading.value = false
    mockFetch.mockReset()
  })

  // ── createProject ──────────────────────────────────────────────────

  describe('createProject', () => {
    it('calls POST /api/project/create and sets currentProject', async () => {
      const { createProject } = await import('../composables/useProject')
      const fakeMeta = {
        version: 1, name: 'Test', author: '', status: 'ready',
        template_id: 'research_paper', tags: [],
        created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
        vcs: { initialized: false }, env: { type: null, path: null },
      }
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          project_path: '/tmp/Test',
          metadata: fakeMeta,
          warnings: [],
        }),
      })

      const result = await createProject({
        name: 'Test',
        location: '/tmp',
        template_id: 'research_paper',
        init_git: false,
      })

      expect(mockFetch).toHaveBeenCalledTimes(1)
      const [url, opts] = mockFetch.mock.calls[0]
      expect(url).toContain('/api/project/create')
      expect(opts.method).toBe('POST')
      expect(result.project_path).toBe('/tmp/Test')
      expect(currentProject.value).not.toBeNull()
      expect(currentProject.value!.name).toBe('Test')
    })

    it('throws on non-ok response', async () => {
      const { createProject } = await import('../composables/useProject')
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 422,
        json: () => Promise.resolve({ detail: 'Invalid name' }),
      })

      await expect(createProject({
        name: 'bad:name',
        location: '/tmp',
      })).rejects.toThrow()
      expect(currentProject.value).toBeNull()
    })
  })

  // ── openProject ────────────────────────────────────────────────────

  describe('openProject', () => {
    it('calls GET /api/project/load and sets currentProject', async () => {
      const { openProject } = await import('../composables/useProject')
      const fakeMeta = {
        version: 1, name: 'Opened', author: 'Author',
        status: 'ready', template_id: 'research_paper', tags: [],
        created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
        vcs: { initialized: true }, env: { type: null, path: null },
      }
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(fakeMeta),
      })

      await openProject('/tmp/Opened')

      expect(mockFetch).toHaveBeenCalledTimes(1)
      const [url] = mockFetch.mock.calls[0]
      expect(url).toContain('/api/project/load')
      expect(url).toContain(encodeURIComponent('/tmp/Opened'))
      expect(currentProject.value).not.toBeNull()
      expect(currentProject.value!.name).toBe('Opened')
    })

    it('throws on 404', async () => {
      const { openProject } = await import('../composables/useProject')
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
        json: () => Promise.resolve({ detail: 'Not found' }),
      })

      await expect(openProject('/nonexistent')).rejects.toThrow()
      expect(currentProject.value).toBeNull()
    })
  })

  // ── loadRecentProjects ─────────────────────────────────────────────

  describe('loadRecentProjects', () => {
    it('fetches and populates recentProjects', async () => {
      const { loadRecentProjects } = await import('../composables/useProject')
      const fakeRecent = [
        { path: '/tmp/A', name: 'A', template_id: 'research_paper', opened_at: '2026-01-01T00:00:00Z' },
        { path: '/tmp/B', name: 'B', template_id: 'blank', opened_at: '2026-01-02T00:00:00Z' },
      ]
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(fakeRecent),
      })

      await loadRecentProjects()

      expect(recentProjects.value).toHaveLength(2)
      expect(recentProjects.value[0].name).toBe('A')
    })

    it('handles empty list', async () => {
      const { loadRecentProjects } = await import('../composables/useProject')
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve([]),
      })

      await loadRecentProjects()
      expect(recentProjects.value).toHaveLength(0)
    })
  })

  // ── closeProject ───────────────────────────────────────────────────

  describe('closeProject', () => {
    it('clears currentProject', async () => {
      const { openProject, closeProject } = await import('../composables/useProject')
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ version: 1, name: 'X', status: 'ready', template_id: 'blank', tags: [], created_at: '', updated_at: '', vcs: { initialized: false }, env: { type: null, path: null } }),
      })
      await openProject('/tmp/X')
      expect(currentProject.value).not.toBeNull()

      closeProject()
      expect(currentProject.value).toBeNull()
    })
  })

  // ── detectProject ──────────────────────────────────────────────────

  describe('detectProject', () => {
    it('returns true for existing project', async () => {
      const { detectProject } = await import('../composables/useProject')
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ is_project: true, metadata: { name: 'Detected' } }),
      })

      const result = await detectProject('/tmp/Detected')
      expect(result).toBe(true)
    })

    it('returns false for non-project', async () => {
      const { detectProject } = await import('../composables/useProject')
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ is_project: false, metadata: null }),
      })

      const result = await detectProject('/tmp/Empty')
      expect(result).toBe(false)
    })
  })
})
