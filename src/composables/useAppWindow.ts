import { ref } from 'vue'
import { getCurrentWindow } from '@tauri-apps/api/window'

/**
 * Application window controls and agent-only window detection.
 *
 * `isAgentOnly` is determined once at creation by inspecting the URL param
 * `agent-only=1` (set by AgentPanel's openAgentWindow). URL params survive
 * cross-window navigation in Tauri (unlike sessionStorage which is
 * window-isolated). The URL is cleaned after detection so a refresh does not
 * accidentally re-enter agent-only mode.
 */
export function useAppWindow() {
  const isAgentOnly = ref(false)
  {
    const _params = new URLSearchParams(window.location.search)
    if (_params.get('agent-only') === '1') {
      isAgentOnly.value = true
      // Clean the URL so refreshing doesn't re-enter agent-only mode accidentally
      const cleanUrl = window.location.pathname
      window.history.replaceState({}, '', cleanUrl)
    }
  }

  // `npm run dev` is also a supported frontend workflow. Tauri's window API
  // throws during setup when the page runs in a regular browser, which would
  // otherwise prevent Vue from mounting at all.
  const appWindow =
    typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window ? getCurrentWindow() : null

  async function handleMinimize() {
    await appWindow?.minimize()
  }

  async function handleToggleMaximize() {
    await appWindow?.toggleMaximize()
  }

  async function handleClose() {
    await appWindow?.close()
  }

  async function onAgentWindowClose() {
    if (isAgentOnly.value && appWindow) {
      await appWindow.close()
    }
  }

  return {
    isAgentOnly,
    handleMinimize,
    handleToggleMaximize,
    handleClose,
    onAgentWindowClose,
  }
}
