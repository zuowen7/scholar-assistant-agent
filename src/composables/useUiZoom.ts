import { ref } from 'vue'
import { getCurrentWebview } from '@tauri-apps/api/webview'

const UI_ZOOM_MIN = 0.8
const UI_ZOOM_MAX = 2
const UI_ZOOM_STEP = 0.1

function loadUiZoom(): number {
  try {
    const saved = Number(localStorage.getItem('ui-zoom') || '1')
    return Number.isFinite(saved) ? Math.min(UI_ZOOM_MAX, Math.max(UI_ZOOM_MIN, saved)) : 1
  } catch { return 1 }
}

/**
 * UI zoom state and controls.
 * Persists to localStorage and applies via Tauri webview setZoom
 * (falls back to CSS `zoom` in non-Tauri environments).
 */
export function useUiZoom() {
  const uiZoom = ref(loadUiZoom())

  async function applyUiZoom(value: number) {
    const normalized = Math.round(Math.min(UI_ZOOM_MAX, Math.max(UI_ZOOM_MIN, value)) * 10) / 10
    uiZoom.value = normalized
    try { localStorage.setItem('ui-zoom', String(normalized)) } catch { /* storage can be unavailable */ }
    try {
      await getCurrentWebview().setZoom(normalized)
    } catch {
      document.documentElement.style.setProperty('zoom', String(normalized))
    }
  }

  function handleUiZoomShortcut(event: KeyboardEvent) {
    if (!(event.ctrlKey || event.metaKey) || event.altKey) return
    if (event.key === '0') {
      event.preventDefault()
      void applyUiZoom(1)
    } else if (event.key === '+' || event.key === '=') {
      event.preventDefault()
      void applyUiZoom(uiZoom.value + UI_ZOOM_STEP)
    } else if (event.key === '-' || event.key === '_') {
      event.preventDefault()
      void applyUiZoom(uiZoom.value - UI_ZOOM_STEP)
    }
  }

  return {
    uiZoom,
    applyUiZoom,
    handleUiZoomShortcut,
    UI_ZOOM_MIN,
    UI_ZOOM_MAX,
    UI_ZOOM_STEP,
  }
}
