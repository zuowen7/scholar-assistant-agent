import { ref, watch } from 'vue'
import { logger } from '../utils/logger'

/**
 * Application theme (dark/light).
 * - `isDark` is the source of truth; a watcher applies it to <html data-theme>.
 * - `toggleTheme` uses the View Transition API for a cinematic circle-clip
 *   dissolve when available, falling back to an instant swap.
 * - Persistence to localStorage is handled by the caller (App.vue onMounted)
 *   so initial boot order stays explicit.
 */
export function useAppTheme() {
  const isDark = ref(false)

  function applyTheme(dark: boolean) {
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
  }

  // Apply immediately on creation so the very first paint matches isDark.
  watch(() => isDark.value, applyTheme, { immediate: true })

  function toggleTheme(e?: MouseEvent) {
    const doc = document.documentElement
    // Capture click position as circle-clip origin
    if (e) {
      doc.style.setProperty('--vt-x', `${e.clientX}px`)
      doc.style.setProperty('--vt-y', `${e.clientY}px`)
    } else {
      doc.style.setProperty('--vt-x', '50%')
      doc.style.setProperty('--vt-y', '50%')
    }
    // View Transition API: cinematic circle-clip dissolve
    if ('startViewTransition' in document) {
      ;(
        document as Document & { startViewTransition: (cb: () => void) => void }
      ).startViewTransition(() => {
        isDark.value = !isDark.value
        try {
          localStorage.setItem('theme', isDark.value ? 'dark' : 'light')
        } catch (err) {
          logger.warn('saveTheme failed:', err)
        }
      })
    } else {
      isDark.value = !isDark.value
      try {
        localStorage.setItem('theme', isDark.value ? 'dark' : 'light')
      } catch (err) {
        logger.warn('saveTheme failed:', err)
      }
    }
  }

  return { isDark, applyTheme, toggleTheme }
}
