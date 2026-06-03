import { ref } from 'vue'
import type { AppMode } from '../types'

export const appMode = ref<AppMode>('editor')
export const showAgentChat = ref(false)
export const modeTransition = ref(false)

export function useAppMode() {
  function setMode(mode: AppMode) {
    appMode.value = mode
    modeTransition.value = true
    setTimeout(() => { modeTransition.value = false }, 300)
  }

  function toggleAgentChat(force?: boolean) {
    showAgentChat.value = force ?? !showAgentChat.value
  }

  return {
    appMode,
    showAgentChat,
    modeTransition,
    setMode,
    toggleAgentChat,
  }
}
