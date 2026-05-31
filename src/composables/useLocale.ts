import { ref } from 'vue'
import type { SupportedLocale } from '../i18n'
import { SUPPORTED_LOCALES, i18n } from '../i18n'

const STORAGE_KEY = 'lang'

function detectSystemLocale(): SupportedLocale {
  const nav = navigator.language
  if (nav.startsWith('en')) return 'en-US'
  return 'zh-CN'
}

function getStoredLocale(): SupportedLocale | null {
  const stored = localStorage.getItem(STORAGE_KEY)
  if (stored && SUPPORTED_LOCALES.includes(stored as SupportedLocale)) {
    return stored as SupportedLocale
  }
  return null
}

function persist(val: SupportedLocale) {
  localStorage.setItem(STORAGE_KEY, val)
  document.documentElement.lang = val
  i18n.global.locale.value = val
}

export const currentLocale = ref<SupportedLocale>(getStoredLocale() ?? detectSystemLocale())

if (typeof document !== 'undefined') {
  document.documentElement.lang = currentLocale.value
  i18n.global.locale.value = currentLocale.value
}

export function useLocale() {
  function setLocale(loc: SupportedLocale) {
    currentLocale.value = loc
    persist(loc)
  }

  return { currentLocale, setLocale }
}

export function _resetLocale() {
  currentLocale.value = getStoredLocale() ?? detectSystemLocale()
}
