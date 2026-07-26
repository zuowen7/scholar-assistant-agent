import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  _resetWorkspaceNavigationForTesting,
  useWorkspaceNavigation,
} from '../composables/useWorkspaceNavigation'

describe('useWorkspaceNavigation', () => {
  beforeEach(() => {
    localStorage.clear()
    _resetWorkspaceNavigationForTesting()
  })

  it('starts at the application home', () => {
    expect(useWorkspaceNavigation().location.value).toEqual({ kind: 'home' })
  })

  it('enters one workspace with one authoritative section', () => {
    const workspace = useWorkspaceNavigation()
    workspace.enterWorkspace('D:\\papers\\demo', { section: 'review', draftView: 'outline' })

    expect(workspace.location.value).toEqual({
      kind: 'workspace',
      projectRoot: 'D:/papers/demo',
      section: 'review',
    })
    expect(workspace.draftView.value).toBe('outline')

    workspace.navigate('draft')
    expect(workspace.location.value).toMatchObject({ kind: 'workspace', section: 'draft' })
  })

  it('persists and restores the last draft view per workspace', () => {
    const workspace = useWorkspaceNavigation()
    workspace.enterWorkspace('D:/papers/demo')
    workspace.setDraftView('mindmap')
    workspace.goHome()
    workspace.enterWorkspace('D:/papers/demo', { restoreView: true })

    expect(workspace.draftView.value).toBe('mindmap')
  })

  it('opens translation as a standalone flow when no workspace is active', () => {
    const workspace = useWorkspaceNavigation()
    workspace.navigate('sources')
    expect(workspace.location.value).toEqual({ kind: 'standalone-translation' })
  })

  it('returns from standalone translation to the last workspace', () => {
    const workspace = useWorkspaceNavigation()
    workspace.enterWorkspace('D:/papers/demo')
    workspace.openStandaloneTranslation()
    workspace.navigate('review')

    expect(workspace.location.value).toEqual({
      kind: 'workspace',
      projectRoot: 'D:/papers/demo',
      section: 'review',
    })
  })

  it('owns the agent dock state', () => {
    const workspace = useWorkspaceNavigation()
    workspace.toggleAgentDock(true)
    expect(workspace.rightDock.value).toBe('agent')
    workspace.toggleAgentDock(false)
    expect(workspace.rightDock.value).toBeNull()
  })

  it('treats export as a project workspace section', () => {
    const workspace = useWorkspaceNavigation()
    workspace.enterWorkspace('D:/papers/demo')
    workspace.navigate('export')
    expect(workspace.location.value).toMatchObject({ kind: 'workspace', section: 'export' })
  })

  it('clears transition state after the navigation motion', () => {
    vi.useFakeTimers()
    const workspace = useWorkspaceNavigation()
    workspace.goHome()
    expect(workspace.modeTransition.value).toBe(true)
    vi.advanceTimersByTime(240)
    expect(workspace.modeTransition.value).toBe(false)
    vi.useRealTimers()
  })
})
