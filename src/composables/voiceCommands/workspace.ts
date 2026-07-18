import { nextTick } from 'vue'
import { useAppMode } from '../useAppMode'

export type VoiceWorkspace = 'translate' | 'write' | 'mindmap' | 'review'

/**
 * Make the production consumer for a voice command reachable before its DOM
 * event is dispatched. KeepAlive preserves mounted workspaces, but a workspace
 * that has never been opened has no listener yet.
 */
export async function activateVoiceWorkspace(workspace: VoiceWorkspace) {
  const { setMode } = useAppMode()
  if (workspace === 'translate') setMode('translate')
  else if (workspace === 'review') setMode('argument')
  else setMode('editor')

  window.dispatchEvent(new CustomEvent('shell-section-change', { detail: workspace }))
  await nextTick()

  if (workspace === 'mindmap') {
    window.dispatchEvent(new CustomEvent('voice-set-mindmap'))
    await nextTick()
  }
}
