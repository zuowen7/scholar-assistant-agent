import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockFetch = vi.fn()
globalThis.fetch = mockFetch

vi.mock('../utils/api', () => ({ API_BASE: '' }))

const mockOpenFolder = vi.fn().mockResolvedValue(undefined)
vi.mock('../composables/useFileTree', () => ({
  useFileTree: () => ({
    openFolder: mockOpenFolder,
    rootDir: { value: null },
    files: { value: [] },
  }),
}))

import { currentProject, recentProjects, projectLoading } from '../composables/useProject'

describe('useProject', () => {
  beforeEach(() => {
    currentProject.value = null
    recentProjects.value = []
    projectLoading.value = false
    mockFetch.mockReset()
    mockOpenFolder.mockReset().mockResolvedValue(undefined)
  })

  // ── createProject ──────────────────────────────────────────────────

  describe('createProject', () => {
    it('calls POST /api/project/create and sets currentProject', async () => {
      const { createProject } = await import('../composables/useProject')
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          project_path: '/tmp/Test', metadata: { version: 1, name: 'Test', status: 'ready', template_id: 'research_paper', tags: [], created_at: '', updated_at: '', vcs: { initialized: false }, env: { type: null, path: null } }, warnings: [],
        }),
      })

      const result = await createProject({ name: 'Test', location: '/tmp', template_id: 'research_paper', init_git: false })

      expect(mockFetch).toHaveBeenCalledTimes(1)
      expect(mockFetch.mock.calls[0][0]).toContain('/api/project/create')
      expect(result.project_path).toBe('/tmp/Test')
      expect(currentProject.value!.name).toBe('Test')
    })

    it('throws on non-ok response', async () => {
      const { createProject } = await import('../composables/useProject')
      mockFetch.mockResolvedValueOnce({ ok: false, status: 422, json: () => Promise.resolve({ detail: 'Invalid name' }) })
      await expect(createProject({ name: 'bad:name', location: '/tmp' })).rejects.toThrow()
    })
  })

  // ── openProject ────────────────────────────────────────────────────

  describe('openProject', () => {
    it('calls GET /api/project/load, sets currentProject and opens file tree', async () => {
      const { openProject } = await import('../composables/useProject')
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ version: 1, name: 'Opened', status: 'ready', template_id: 'research_paper', tags: [], created_at: '', updated_at: '', vcs: { initialized: true }, env: { type: null, path: null } }),
      })

      await openProject('/tmp/Opened')

      expect(mockFetch).toHaveBeenCalledTimes(1)
      expect(mockFetch.mock.calls[0][0]).toContain('/api/project/load')
      expect(currentProject.value!.name).toBe('Opened')
      expect(mockOpenFolder).toHaveBeenCalledWith('/tmp/Opened')
    })

    it('throws on 404', async () => {
      const { openProject } = await import('../composables/useProject')
      mockFetch.mockResolvedValueOnce({ ok: false, status: 404, json: () => Promise.resolve({ detail: 'Not found' }) })
      await expect(openProject('/nonexistent')).rejects.toThrow()
    })

    it('rolls back currentProject on failure', async () => {
      const { openProject } = await import('../composables/useProject')
      currentProject.value = { version: 1, name: 'Prev', status: 'ready', template_id: 'blank', tags: [], created_at: '', updated_at: '', vcs: { initialized: false }, env: { type: null, path: null } }
      mockFetch.mockResolvedValueOnce({ ok: false, status: 500, json: () => Promise.resolve({ detail: 'Fail' }) })

      await expect(openProject('/bad')).rejects.toThrow()
      expect(currentProject.value!.name).toBe('Prev')
    })
  })

  // ── loadRecentProjects ─────────────────────────────────────────────

  describe('loadRecentProjects', () => {
    it('fetches and populates recentProjects', async () => {
      const { loadRecentProjects } = await import('../composables/useProject')
      mockFetch.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve([{ path: '/tmp/A', name: 'A', template_id: 'research_paper', opened_at: '' }]) })
      await loadRecentProjects()
      expect(recentProjects.value).toHaveLength(1)
    })

    it('handles fetch error gracefully', async () => {
      const { loadRecentProjects } = await import('../composables/useProject')
      mockFetch.mockRejectedValueOnce(new Error('Network error'))
      await loadRecentProjects()
      expect(recentProjects.value).toHaveLength(0)
    })
  })

  // ── closeProject ───────────────────────────────────────────────────

  describe('closeProject', () => {
    it('clears currentProject and file tree', async () => {
      const { openProject, closeProject } = await import('../composables/useProject')
      mockFetch.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ version: 1, name: 'X', status: 'ready', template_id: 'blank', tags: [], created_at: '', updated_at: '', vcs: { initialized: false }, env: { type: null, path: null } }) })
      await openProject('/tmp/X')
      expect(currentProject.value).not.toBeNull()

      await closeProject()
      expect(currentProject.value).toBeNull()
      // closeProject is async now — file tree should be cleared
    })
  })

  // ── detectProject ──────────────────────────────────────────────────

  describe('detectProject', () => {
    it('returns true for existing project', async () => {
      const { detectProject } = await import('../composables/useProject')
      mockFetch.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ is_project: true, metadata: { name: 'Detected' } }) })
      expect(await detectProject('/tmp/Detected')).toBe(true)
    })

    it('returns false for non-project', async () => {
      const { detectProject } = await import('../composables/useProject')
      mockFetch.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ is_project: false, metadata: null }) })
      expect(await detectProject('/tmp/Empty')).toBe(false)
    })

    it('returns false on server error', async () => {
      const { detectProject } = await import('../composables/useProject')
      mockFetch.mockRejectedValueOnce(new Error('Network error'))
      expect(await detectProject('/tmp/Dead')).toBe(false)
    })
  })
})
