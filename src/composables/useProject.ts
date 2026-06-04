import { ref } from 'vue'
import { API_BASE } from '../utils/api'
import type { ProjectMetadata, RecentProject, ProjectTemplate } from '../types'

export const currentProject = ref<ProjectMetadata | null>(null)
export const recentProjects = ref<RecentProject[]>([])
export const projectLoading = ref(false)

export interface CreateProjectRequest {
  name: string
  location: string
  author?: string
  template_id?: string
  init_git?: boolean
}

export interface CreateProjectResponse {
  project_path: string
  metadata: ProjectMetadata
  warnings: string[]
}

function apiUrl(path: string): string {
  return `${API_BASE}${path}`
}

export async function createProject(req: CreateProjectRequest): Promise<CreateProjectResponse> {
  projectLoading.value = true
  try {
    const resp = await fetch(apiUrl('/api/project/create'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: req.name,
        location: req.location,
        author: req.author || '',
        template_id: req.template_id || 'research_paper',
        init_git: req.init_git !== false,
      }),
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }))
      throw new Error(err.detail || `创建项目失败 (${resp.status})`)
    }
    const data: CreateProjectResponse = await resp.json()
    currentProject.value = data.metadata
    return data
  } finally {
    projectLoading.value = false
  }
}

export async function openProject(path: string): Promise<void> {
  projectLoading.value = true
  try {
    const resp = await fetch(apiUrl(`/api/project/load?path=${encodeURIComponent(path)}`))
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }))
      throw new Error(err.detail || `打开项目失败 (${resp.status})`)
    }
    const meta: ProjectMetadata = await resp.json()
    currentProject.value = meta
  } finally {
    projectLoading.value = false
  }
}

export async function loadRecentProjects(): Promise<void> {
  const resp = await fetch(apiUrl('/api/project/recent'))
  if (resp.ok) {
    recentProjects.value = await resp.json()
  }
}

export function closeProject(): void {
  currentProject.value = null
}

export async function detectProject(path: string): Promise<boolean> {
  const resp = await fetch(apiUrl(`/api/project/detect?path=${encodeURIComponent(path)}`), {
    method: 'POST',
  })
  if (!resp.ok) return false
  const data = await resp.json()
  return data.is_project === true
}

export function useProject() {
  return {
    currentProject,
    recentProjects,
    projectLoading,
    createProject,
    openProject,
    loadRecentProjects,
    closeProject,
    detectProject,
  }
}
