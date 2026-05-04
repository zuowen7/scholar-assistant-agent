import { ref } from 'vue'

export interface ToastItem {
  id: number
  level: 'success' | 'warn' | 'danger' | 'info'
  message: string
  duration: number
}

const toasts = ref<ToastItem[]>([])
let nextId = 0

export function useToast() {
  function show(level: ToastItem['level'], message: string, duration = 3000) {
    const id = nextId++
    toasts.value.push({ id, level, message, duration })
    if (duration > 0) {
      setTimeout(() => dismiss(id), duration)
    }
  }

  function dismiss(id: number) {
    toasts.value = toasts.value.filter(t => t.id !== id)
  }

  function success(message: string, duration?: number) { show('success', message, duration) }
  function warn(message: string, duration?: number)    { show('warn', message, duration) }
  function danger(message: string, duration?: number)  { show('danger', message, duration) }
  function info(message: string, duration?: number)    { show('info', message, duration) }

  return { toasts, show, dismiss, success, warn, danger, info }
}
