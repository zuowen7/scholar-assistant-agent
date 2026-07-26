import { nextTick } from 'vue'
import { useWorkspaceNavigation } from '../useWorkspaceNavigation'

export type VoiceWorkspace = 'translate' | 'write' | 'mindmap' | 'review'

/**
 * Make the production consumer for a voice command reachable before its DOM
 * event is dispatched. KeepAlive preserves mounted workspaces, but a workspace
 * that has never been opened has no listener yet.
 */
export async function activateVoiceWorkspace(workspace: VoiceWorkspace) {
  const navigation = useWorkspaceNavigation()
  if (workspace === 'translate') navigation.openStandaloneTranslation()
  else if (workspace === 'review') navigation.navigate('review')
  else navigation.navigate('draft')
  await nextTick()

  if (workspace === 'mindmap') {
    window.dispatchEvent(new CustomEvent('voice-set-mindmap'))
    await nextTick()
  }
}
