import { ref } from 'vue'
import { logger } from '../utils/logger'

export interface ReadSettings {
  fontSize: number
  lineHeight: number
  fontFamily: string
  transColor: string
}

const STORAGE_KEY = 'read-settings'

/**
 * Reading display settings (font size / line height / family / translation color).
 * Persists to localStorage; consumed by the settings center and translation view.
 */
export function useReadSettings() {
  const readSettings = ref<ReadSettings>({
    fontSize: 16,
    lineHeight: 1.9,
    fontFamily: 'system-ui',
    transColor: '',
  })

  function loadReadSettings() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (raw) {
        const parsed = JSON.parse(raw)
        if (parsed && typeof parsed.fontSize === 'number') {
          readSettings.value = { ...readSettings.value, ...parsed }
        }
      }
    } catch (e) {
      logger.warn('loadReadSettings failed:', e)
    }
  }

  function saveReadSettings() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(readSettings.value))
    } catch (e) {
      logger.warn('saveReadSettings failed:', e)
    }
  }

  function onFontSizeChange(value: number) {
    readSettings.value.fontSize = value
    saveReadSettings()
  }

  function onLineHeightChange(value: number) {
    readSettings.value.lineHeight = value / 10
    saveReadSettings()
  }

  function onFontFamilyChange(value: string) {
    readSettings.value.fontFamily = value
    saveReadSettings()
  }

  function onColorChange(value: string) {
    readSettings.value.transColor = value
    saveReadSettings()
  }

  return {
    readSettings,
    loadReadSettings,
    saveReadSettings,
    onFontSizeChange,
    onLineHeightChange,
    onFontFamilyChange,
    onColorChange,
  }
}
