import { ref, onUnmounted } from 'vue'
import { logger } from '../utils/logger'

const isTauri = '__TAURI_INTERNALS__' in window

export function useGlobalHotkey(
  defaultKey: string,
  callback: () => void,
) {
  const currentKey = ref(defaultKey)
  const isRegistered = ref(false)
  const ready = ref(false)

  if (isTauri) {
    registerKey(defaultKey)
  }

  async function registerKey(key: string) {
    if (!isTauri) return
    try {
      const { register } = await import('@tauri-apps/plugin-global-shortcut')
      await register(key, (event) => {
        if (event.state === 'Pressed') callback()
      })
      isRegistered.value = true
      ready.value = true
      logger.debug('[voice] Global hotkey registered:', key)
    } catch (e) {
      logger.warn('[voice] Hotkey register failed:', e)
      isRegistered.value = false
    }
  }

  async function unregisterKey(key: string) {
    if (!isTauri) return
    try {
      const { unregister } = await import('@tauri-apps/plugin-global-shortcut')
      await unregister(key)
    } catch { /* ignore */ }
  }

  async function changeHotkey(newKey: string) {
    await unregisterKey(currentKey.value)
    currentKey.value = newKey
    await registerKey(newKey)
  }

  async function cleanup() {
    if (currentKey.value) {
      await unregisterKey(currentKey.value)
    }
    isRegistered.value = false
  }

  try { onUnmounted(() => cleanup()) } catch { /* not in Vue setup */ }

  return { currentKey, isRegistered, ready, changeHotkey, cleanup }
}
