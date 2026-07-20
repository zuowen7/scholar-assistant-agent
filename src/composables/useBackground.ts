import { ref, computed } from 'vue'
import { open } from '@tauri-apps/plugin-dialog'
import { readFile } from '@tauri-apps/plugin-fs'
import { convertFileSrc } from '@tauri-apps/api/core'
import { useI18n } from 'vue-i18n'
import { useToast } from './useToast'

export interface BackgroundSettings {
  path: string
  type: 'image' | 'video'
  opacity: number
}

const STORAGE_KEY = 'bg-settings'

const VIDEO_EXTS = ['mp4', 'webm', 'mkv', 'avi', 'mov']
const MIME_MAP: Record<string, string> = {
  jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png',
  gif: 'image/gif', bmp: 'image/bmp', webp: 'image/webp',
  svg: 'image/svg+xml',
}

/**
 * Custom background wallpaper (image or video).
 * Persists path/opacity to localStorage and resolves a displayable URL
 * (prefers an in-memory data URL so it works in release builds without
 * the asset protocol scope).
 */
export function useBackground() {
  const { t } = useI18n()
  const { pushError } = useToast()

  const bgSettings = ref<BackgroundSettings>({
    path: '',
    type: 'image',
    opacity: 30,
  })

  // data URL cache — bypasses convertFileSrc / asset protocol (works in release builds)
  const bgDataUrl = ref('')

  const bgAssetUrl = computed(() => {
    // prefer in-memory data URL (works in release builds w/o asset protocol)
    if (bgDataUrl.value) return bgDataUrl.value
    if (!bgSettings.value.path) return ''
    try {
      return convertFileSrc(bgSettings.value.path)
    } catch {
      return ''
    }
  })

  const backgroundLayerStyle = computed(() => {
    const s: Record<string, string> = {}
    const opacity = bgSettings.value.opacity / 100
    if (bgSettings.value.type === 'image' && bgSettings.value.path && bgAssetUrl.value) {
      s['background-image'] = `url("${bgAssetUrl.value}")`
      s['background-size'] = 'cover'
      s['background-position'] = 'center'
      s['background-repeat'] = 'no-repeat'
      s['opacity'] = String(opacity)
    } else if (bgSettings.value.type === 'video' && bgSettings.value.path && bgAssetUrl.value) {
      s['opacity'] = String(opacity)
    } else {
      s['display'] = 'none'
    }
    return s
  })

  function loadBgSettings() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (raw) {
        const parsed = JSON.parse(raw)
        if (parsed && typeof parsed.path === 'string') {
          bgSettings.value = {
            path: parsed.path || '',
            type: parsed.type === 'video' ? 'video' : 'image',
            opacity: typeof parsed.opacity === 'number' ? parsed.opacity : 30,
          }
        }
      }
    } catch {
      // ignore
    }
  }

  function saveBgSettings() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(bgSettings.value))
    } catch {
      // ignore
    }
  }

  async function pathToDataUrl(filePath: string): Promise<string> {
    try {
      const bytes = await readFile(filePath)
      const ext = filePath.split('.').pop()?.toLowerCase() || 'jpg'
      const mime = MIME_MAP[ext] || 'image/jpeg'
      // chunked base64 encode to avoid call stack overflow on large images
      let binary = ''
      for (let i = 0; i < bytes.length; i += 8192) {
        binary += String.fromCharCode(...bytes.subarray(i, Math.min(i + 8192, bytes.length)))
      }
      return `data:${mime};base64,${btoa(binary)}`
    } catch {
      return ''
    }
  }

  async function pickBackground() {
    try {
      const selected = await open({
        multiple: false,
        filters: [
          {
            name: t('app.imageAndVideo'),
            extensions: [
              'jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'svg',
              'mp4', 'webm', 'mkv', 'avi', 'mov',
            ],
          },
          { name: t('app.image'), extensions: ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'svg'] },
          { name: t('app.video'), extensions: ['mp4', 'webm', 'mkv', 'avi', 'mov'] },
          { name: t('app.allFiles'), extensions: ['*'] },
        ],
      })
      if (!selected) return

      const filePath = typeof selected === 'string' ? selected : (selected as string)
      if (!filePath) return

      const ext = filePath.split('.').pop()?.toLowerCase() || ''
      const isVideo = VIDEO_EXTS.includes(ext)

      bgSettings.value = {
        path: filePath,
        type: isVideo ? 'video' : 'image',
        opacity: bgSettings.value.opacity,
      }
      saveBgSettings()
      // generate data URL for reliable display (bypasses asset protocol scope)
      if (!isVideo) {
        bgDataUrl.value = ''
        pathToDataUrl(filePath).then(url => { if (url) bgDataUrl.value = url })
      }
    } catch {
      // Show error to user - might be browser mode or permission issue
      pushError(t('app.bgPickFailed'))
    }
  }

  function clearBackground() {
    bgSettings.value = { path: '', type: 'image', opacity: 30 }
    bgDataUrl.value = ''
    saveBgSettings()
  }

  function onOpacityChange(value: number) {
    bgSettings.value.opacity = value
    saveBgSettings()
  }

  /** Load persisted settings and pre-render the existing image as a data URL. */
  function initBackground() {
    loadBgSettings()
    if (bgSettings.value.path && bgSettings.value.type === 'image') {
      pathToDataUrl(bgSettings.value.path).then(url => { if (url) bgDataUrl.value = url })
    }
  }

  return {
    bgSettings,
    bgDataUrl,
    bgAssetUrl,
    backgroundLayerStyle,
    loadBgSettings,
    saveBgSettings,
    pickBackground,
    pathToDataUrl,
    clearBackground,
    onOpacityChange,
    initBackground,
  }
}
