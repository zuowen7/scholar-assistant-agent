import { ref } from 'vue'

export type WorkspaceSection = 'draft' | 'sources' | 'review' | 'export'
export type DraftView = 'editor' | 'preview' | 'outline' | 'mindmap' | 'latex'
export type RightDock = 'agent' | null

export type AppLocation =
  | { kind: 'home' }
  | { kind: 'standalone-translation' }
  | {
      kind: 'workspace'
      projectRoot: string | null
      section: WorkspaceSection
    }

const location = ref<AppLocation>({ kind: 'home' })
const draftView = ref<DraftView>('editor')
const rightDock = ref<RightDock>(null)
const modeTransition = ref(false)
let lastWorkspaceLocation: Extract<AppLocation, { kind: 'workspace' }> | null = null

let transitionTimer: ReturnType<typeof setTimeout> | null = null

function normalizedRoot(root: string | null | undefined): string | null {
  const trimmed = root?.trim()
  return trimmed ? trimmed.replace(/\\/g, '/').replace(/\/+$/, '') : null
}

function storageKey(root: string): string {
  return `yanmo:workspace-view:${root.toLowerCase()}`
}

function persistedDraftView(root: string | null): DraftView | null {
  if (!root || typeof localStorage === 'undefined') return null
  const value = localStorage.getItem(storageKey(root))
  return ['editor', 'preview', 'outline', 'mindmap', 'latex'].includes(value || '')
    ? (value as DraftView)
    : null
}

function beginTransition() {
  modeTransition.value = true
  if (transitionTimer) clearTimeout(transitionTimer)
  transitionTimer = setTimeout(() => {
    modeTransition.value = false
    transitionTimer = null
  }, 240)
}

function setLocation(next: AppLocation) {
  location.value = next
  beginTransition()
}

function goHome() {
  setLocation({ kind: 'home' })
}

function openStandaloneTranslation() {
  setLocation({ kind: 'standalone-translation' })
}

function enterWorkspace(
  projectRoot: string | null | undefined,
  options: { section?: WorkspaceSection; draftView?: DraftView; restoreView?: boolean } = {},
) {
  const root = normalizedRoot(projectRoot)
  const nextDraftView =
    options.draftView || (options.restoreView ? persistedDraftView(root) : null) || 'editor'
  draftView.value = nextDraftView
  if (rightDock.value === null) rightDock.value = 'agent'
  const nextLocation: Extract<AppLocation, { kind: 'workspace' }> = {
    kind: 'workspace',
    projectRoot: root,
    section: options.section || 'draft',
  }
  lastWorkspaceLocation = nextLocation
  setLocation(nextLocation)
}

function navigate(section: WorkspaceSection) {
  const current = location.value
  if (current.kind !== 'workspace') {
    if (section === 'sources') openStandaloneTranslation()
    else if (lastWorkspaceLocation) {
      const next = { ...lastWorkspaceLocation, section }
      lastWorkspaceLocation = next
      setLocation(next)
    }
    return
  }
  const next = { ...current, section }
  lastWorkspaceLocation = next
  setLocation(next)
}

function setDraftView(view: DraftView) {
  draftView.value = view
  const current = location.value
  if (current.kind === 'workspace' && current.projectRoot && typeof localStorage !== 'undefined') {
    localStorage.setItem(storageKey(current.projectRoot), view)
  }
  if (current.kind === 'workspace' && current.section !== 'draft') {
    setLocation({ ...current, section: 'draft' })
  }
}

function setRightDock(dock: RightDock) {
  rightDock.value = dock
}

function toggleAgentDock(force?: boolean) {
  const open = force ?? rightDock.value !== 'agent'
  rightDock.value = open ? 'agent' : null
}

export function useWorkspaceNavigation() {
  return {
    location,
    draftView,
    rightDock,
    modeTransition,
    goHome,
    openStandaloneTranslation,
    enterWorkspace,
    navigate,
    setDraftView,
    setRightDock,
    toggleAgentDock,
  }
}

export function _resetWorkspaceNavigationForTesting() {
  if (transitionTimer) clearTimeout(transitionTimer)
  transitionTimer = null
  location.value = { kind: 'home' }
  draftView.value = 'editor'
  rightDock.value = null
  modeTransition.value = false
  lastWorkspaceLocation = null
}
