import { describe, it, expect, vi, beforeEach } from 'vitest'

function rst(status: number, body: any) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => 'application/json' },
    json: () => Promise.resolve(body),
  }
}

function rstHtml(status: number) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => 'text/html' },
    text: () => Promise.resolve('<html>Error</html>'),
    json: () => Promise.reject(new Error('Not JSON')),
  }
}

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

function meta(name: string) {
  return { version: 1, name, status: 'ready', template_id: 'research_paper', tags: [], created_at: '', updated_at: '', vcs: { initialized: false }, env: { type: null, path: null } }
}

describe('useProject', () => {
  beforeEach(() => {
    currentProject.value = null
    recentProjects.value = []
    projectLoading.value = false
    mockFetch.mockReset()
    mockOpenFolder.mockReset().mockResolvedValue(undefined)
  })

  describe('createProject', () => {
    it('calls POST /api/project/create and sets currentProject', async () => {
      const { createProject } = await import('../composables/useProject')
      mockFetch.mockResolvedValueOnce(rst(200, { project_path: '/tmp/Test', metadata: meta('Test'), warnings: [] }))
      const result = await createProject({ name: 'Test', location: '/tmp', init_git: false })
      expect(mockFetch.mock.calls[0][0]).toContain('/api/project/create')
      expect(result.project_path).toBe('/tmp/Test')
      expect(currentProject.value!.name).toBe('Test')
    })

    it('throws on non-ok response', async () => {
      const { createProject } = await import('../composables/useProject')
      mockFetch.mockResolvedValueOnce(rst(422, { detail: 'Invalid name' }))
      await expect(createProject({ name: 'bad:name', location: '/tmp' })).rejects.toThrow()
    })

    it('handles HTML error page on non-ok', async () => {
      const { createProject } = await import('../composables/useProject')
      mockFetch.mockResolvedValueOnce(rstHtml(500))
      await expect(createProject({ name: 'X', location: '/tmp' })).rejects.toThrow()
    })
  })

  describe('openProject', () => {
    it('calls GET /api/project/load, sets currentProject and opens file tree', async () => {
      const { openProject } = await import('../composables/useProject')
      mockFetch.mockResolvedValueOnce(rst(200, meta('Opened')))
      await openProject('/tmp/Opened')
      expect(mockFetch.mock.calls[0][0]).toContain('/api/project/load')
      expect(currentProject.value!.name).toBe('Opened')
      expect(mockOpenFolder).toHaveBeenCalledWith('/tmp/Opened')
    })

    it('throws on 404', async () => {
      const { openProject } = await import('../composables/useProject')
      mockFetch.mockResolvedValueOnce(rst(404, { detail: 'Not found' }))
      await expect(openProject('/nonexistent')).rejects.toThrow()
    })

    it('rolls back currentProject on failure', async () => {
      const { openProject } = await import('../composables/useProject')
      currentProject.value = meta('Prev')
      mockFetch.mockResolvedValueOnce(rst(500, { detail: 'Fail' }))
      await expect(openProject('/bad')).rejects.toThrow()
      expect(currentProject.value!.name).toBe('Prev')
    })
  })

  describe('loadRecentProjects', () => {
    it('fetches and populates recentProjects', async () => {
      const { loadRecentProjects } = await import('../composables/useProject')
      mockFetch.mockResolvedValueOnce(rst(200, [{ path: '/tmp/A', name: 'A', template_id: 'b', opened_at: '' }]))
      await loadRecentProjects()
      expect(recentProjects.value).toHaveLength(1)
    })

    it('handles fetch error gracefully', async () => {
      const { loadRecentProjects } = await import('../composables/useProject')
      mockFetch.mockRejectedValueOnce(new Error('fail'))
      await loadRecentProjects()
      expect(recentProjects.value).toHaveLength(0)
    })

    it('handles non-array response gracefully', async () => {
      const { loadRecentProjects } = await import('../composables/useProject')
      mockFetch.mockResolvedValueOnce(rst(200, { error: 'not array' }))
      await loadRecentProjects()
      expect(recentProjects.value).toHaveLength(0)
    })
  })

  describe('closeProject', () => {
    it('clears currentProject and file tree', async () => {
      const { openProject, closeProject } = await import('../composables/useProject')
      mockFetch.mockResolvedValueOnce(rst(200, meta('X')))
      await openProject('/tmp/X')
      expect(currentProject.value).not.toBeNull()
      await closeProject()
      expect(currentProject.value).toBeNull()
    })
  })

  describe('detectProject', () => {
    it('returns true for existing project', async () => {
      const { detectProject } = await import('../composables/useProject')
      mockFetch.mockResolvedValueOnce(rst(200, { is_project: true, metadata: { name: 'D' } }))
      expect(await detectProject('/tmp/D')).toBe(true)
    })

    it('returns false for non-project', async () => {
      const { detectProject } = await import('../composables/useProject')
      mockFetch.mockResolvedValueOnce(rst(200, { is_project: false, metadata: null }))
      expect(await detectProject('/tmp/E')).toBe(false)
    })

    it('returns false on server error', async () => {
      const { detectProject } = await import('../composables/useProject')
      mockFetch.mockRejectedValueOnce(new Error('fail'))
      expect(await detectProject('/tmp/Dead')).toBe(false)
    })

    it('returns false on HTML response', async () => {
      const { detectProject } = await import('../composables/useProject')
      mockFetch.mockResolvedValueOnce(rstHtml(200))
      expect(await detectProject('/tmp/HTML')).toBe(false)
    })
  })
})
