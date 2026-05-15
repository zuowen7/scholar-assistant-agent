import { ref } from 'vue'

export interface ToastItem {
  id: number
  level: 'success' | 'warn' | 'danger' | 'info'
  message: string
  duration: number
}

export interface ErrorLogEntry {
  id: number
  level: 'warn' | 'danger'
  message: string
  ts: string
}

export const toasts = ref<ToastItem[]>([])
export const errorLog = ref<ErrorLogEntry[]>([])
export const unreadErrorCount = ref(0)
let nextId = 0

export function clearErrorLog() {
  errorLog.value = []
  unreadErrorCount.value = 0
}

export function markErrorsRead() {
  unreadErrorCount.value = 0
}

export function useToast() {
  function show(level: ToastItem['level'], message: string, duration = 3000) {
    const id = nextId++
    toasts.value.push({ id, level, message, duration })
    if (duration > 0) {
      setTimeout(() => dismiss(id), duration)
    }
    if (level === 'danger' || level === 'warn') {
      const ts = new Date().toLocaleTimeString('zh-CN', { hour12: false })
      errorLog.value.unshift({ id, level, message, ts })
      if (errorLog.value.length > 50) errorLog.value.length = 50
      unreadErrorCount.value++
    }
  }

  function dismiss(id: number) {
    toasts.value = toasts.value.filter(t => t.id !== id)
  }

  function success(message: string, duration?: number) { show('success', message, duration) }
  function warn(message: string, duration?: number)    { show('warn', message, duration) }
  function danger(message: string, duration?: number)  { show('danger', message, duration) }
  function info(message: string, duration?: number)    { show('info', message, duration) }

  // Semantic aliases used by error-handling paths across the app
  function pushError(message: string, duration = 7000) { show('danger', message, duration) }
  function pushWarning(message: string, duration = 5000) { show('warn', message, duration) }

  return { toasts, show, dismiss, success, warn, danger, info, pushError, pushWarning }
}

/**
 * Extract a human-readable message from a fetch error or API response body
 * and push it as a toast.  Aborts (user-initiated cancel) are silenced.
 */
export function toastFromError(err: unknown): void {
  // AbortError = user cancelled — stay silent
  if (err instanceof DOMException && err.name === 'AbortError') return
  if (err instanceof Error && err.message === 'AbortError') return

  const { pushError } = useToast()

  if (err instanceof Error) { pushError(err.message); return }
  if (typeof err === 'string') { pushError(err); return }
  if (err && typeof err === 'object') {
    const o = err as Record<string, unknown>
    // Backend structured: { error: { code, message } } or { error: "string" }
    const inner = o['error']
    const msg = o['message'] ?? (inner && typeof inner === 'object'
      ? (inner as Record<string, unknown>)['message']
      : inner)
    if (msg) { pushError(String(msg)); return }
  }
  pushError('未知错误，请检查网络或后端状态')
}
