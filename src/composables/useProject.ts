import { ref } from 'vue'
import { API_BASE } from '../utils/api'
import type { ProjectMetadata, RecentProject } from '../types'
import { activeTabId, tabs } from './useEditorState'
import { useFileTree } from './useFileTree'

export const currentProject = ref<ProjectMetadata | null>(null)
export const currentWorkspaceGrant = ref<string | null>(null)
export const recentProjects = ref<RecentProject[]>([])
export const projectLoading = ref(false)

// Concurrency guard tokens
let _operationId = 0

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
  workspace_grant: string
}

function apiUrl(path: string): string {
  return `${API_BASE}${path}`
}

async function parseResponse<T = unknown>(resp: Response): Promise<T> {
  const contentType = resp.headers.get('content-type') || ''
  if (!contentType.includes('application/json')) {
    const text = await resp.text().catch(() => '')
    throw new Error(text.slice(0, 200) || `服务器返回非 JSON 响应 (${resp.status})`)
  }
  return resp.json() as Promise<T>
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
      const err = await parseResponse<{ detail?: string }>(resp).catch(() => ({
        detail: resp.statusText,
      }))
      throw new Error(err.detail || `创建项目失败 (${resp.status})`)
    }
    const data = await parseResponse<CreateProjectResponse>(resp)
    currentProject.value = data.metadata
    currentWorkspaceGrant.value = data.workspace_grant
    return data
  } finally {
    projectLoading.value = false
  }
}

export async function openProject(path: string): Promise<void> {
  const thisOp = ++_operationId
  projectLoading.value = true
  const prevProject = currentProject.value
  const prevWorkspaceGrant = currentWorkspaceGrant.value
  let prevRootDir: string | null = null
  try {
    const fileTree = useFileTree()
    prevRootDir = fileTree.rootDir.value

    // A project switch must never discard unsaved Monaco content. Clean tabs
    // are cleared after the new project has loaded successfully; dirty tabs
    // require the user to save or explicitly close the current project first.
    if (tabs.value.some((tab) => tab.isModified)) {
      throw new Error('当前项目有未保存的编辑内容，请先保存或关闭当前项目后再切换。')
    }

    const resp = await fetch(apiUrl(`/api/project/load?path=${encodeURIComponent(path)}`))
    if (!resp.ok) {
      const err = await parseResponse<{ detail?: string }>(resp).catch(() => ({
        detail: resp.statusText,
      }))
      throw new Error(err.detail || `打开项目失败 (${resp.status})`)
    }
    const meta = (await parseResponse(resp)) as ProjectMetadata & { workspace_grant?: string }
    if (thisOp !== _operationId) return
    try {
      await fileTree.openFolder(path)
    } catch {
      /* Non-Tauri */
    }
    if (thisOp !== _operationId) return
    currentProject.value = meta
    currentWorkspaceGrant.value = meta.workspace_grant || null
    tabs.value = []
    activeTabId.value = null
  } catch (err) {
    // Only roll back if no newer operation has started
    if (thisOp === _operationId) {
      currentProject.value = prevProject
      currentWorkspaceGrant.value = prevWorkspaceGrant
      if (prevRootDir) {
        try {
          await useFileTree().openFolder(prevRootDir)
        } catch {
          /* */
        }
      }
    }
    throw err
  } finally {
    projectLoading.value = false
  }
}

export async function removeRecentProject(path: string): Promise<void> {
  try {
    await fetch(apiUrl(`/api/project/recent?path=${encodeURIComponent(path)}`), {
      method: 'DELETE',
    })
    recentProjects.value = recentProjects.value.filter((p) => p.path !== path)
  } catch {
    /* */
  }
}

export async function loadRecentProjects(): Promise<void> {
  try {
    const resp = await fetch(apiUrl('/api/project/recent'))
    if (resp.ok) {
      const data = await parseResponse<RecentProject[] | null>(resp).catch(() => null)
      if (Array.isArray(data)) recentProjects.value = data
    }
  } catch {
    /* */
  }
}

export async function closeProject(): Promise<void> {
  currentProject.value = null
  currentWorkspaceGrant.value = null
  const { rootDir, files } = useFileTree()
  rootDir.value = null
  files.value = []
  tabs.value = []
  activeTabId.value = null
}

export async function detectProject(path: string): Promise<boolean> {
  try {
    const resp = await fetch(apiUrl(`/api/project/detect?path=${encodeURIComponent(path)}`), {
      method: 'POST',
    })
    if (!resp.ok) return false
    const data = await parseResponse<{ is_project: boolean }>(resp).catch(() => ({
      is_project: false,
    }))
    return data.is_project === true
  } catch {
    return false
  }
}

export function useProject() {
  return {
    currentProject,
    currentWorkspaceGrant,
    recentProjects,
    projectLoading,
    createProject,
    openProject,
    loadRecentProjects,
    removeRecentProject,
    closeProject,
    detectProject,
  }
}
