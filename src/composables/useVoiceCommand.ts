import { ref } from 'vue'
import { useSpeechRecognition } from './useSpeechRecognition'

const isTauri = '__TAURI_INTERNALS__' in window

function getVoiceLanguage(): string {
  try {
    const raw = localStorage.getItem('voice-settings')
    if (raw) {
      const s = JSON.parse(raw)
      if (s.language) return s.language
    }
  } catch { /* ignore */ }
  return 'zh-CN'
}

export type VoiceCommandState = 'idle' | 'activating' | 'listening' | 'submitting' | 'processing'

// ── Module-level singleton state ───────────────────────────────────────

const state = ref<VoiceCommandState>('idle')
const transcript = ref('')
const response = ref('')
const error = ref('')

let timeoutHandle: ReturnType<typeof setTimeout> | null = null
let silenceHandle: ReturnType<typeof setTimeout> | null = null
let speechStarted = false

function clearTimeout_() {
  if (timeoutHandle !== null) { clearTimeout(timeoutHandle); timeoutHandle = null }
  if (silenceHandle !== null) { clearTimeout(silenceHandle); silenceHandle = null }
}

function submit() {
  clearTimeout_()
  const text = transcript.value.trim()
  if (!text) { cancel(); return }
  state.value = 'submitting'
  console.log('[voice] submitting:', text)
  window.dispatchEvent(new CustomEvent('voice-command-submit', {
    detail: { text },
  }))
}

function cancel() {
  clearTimeout_()
  if (speechStarted) {
    speech.stop()
    speechStarted = false
  }
  state.value = 'idle'
}

// Silence-based auto-submit: 2s after last speech result, auto-submit
const SILENCE_MS = 2000

const speech = useSpeechRecognition({
  onResult(text: string) {
    if (state.value === 'listening' || state.value === 'activating') {
      transcript.value = text
      // Reset silence timer on each result
      if (silenceHandle !== null) clearTimeout(silenceHandle)
      if (text.trim()) {
        silenceHandle = setTimeout(() => {
          if (state.value === 'listening') submit()
        }, SILENCE_MS)
      }
    }
  },
  onEnd() {
    // If still listening when speech engine stops naturally, submit immediately
    if (state.value === 'listening' && transcript.value.trim()) {
      submit()
    }
  },
})

export function useVoiceCommand() {
  function triggerVoiceCommand() {
    console.log('[voice] triggerVoiceCommand, state=', state.value)
    if (state.value !== 'idle') {
      cancel()
      return
    }

    if (!speech.isSupported) {
      error.value = '当前浏览器不支持语音识别'
      return
    }

    error.value = ''
    transcript.value = ''
    response.value = ''
    state.value = 'activating'

    window.dispatchEvent(new CustomEvent('voice-command-trigger'))

    const activateWindow = async () => {
      if (isTauri) {
        try {
          const { getCurrentWindow } = await import('@tauri-apps/api/window')
          const win = getCurrentWindow()
          await win.unminimize()
          await win.setFocus()
        } catch { /* ignore */ }
      }
    }

    activateWindow().then(() => {
      return new Promise<void>(resolve => {
        timeoutHandle = setTimeout(resolve, 150)
      })
    }).then(() => {
      if (state.value !== 'activating') return
      state.value = 'listening'
      speechStarted = true
      const lang = getVoiceLanguage()
      speech.start(lang)

      // 10s absolute timeout — no speech at all
      timeoutHandle = setTimeout(() => {
        if (state.value === 'listening') {
          error.value = '没有检测到语音'
          cancel()
        }
      }, 10_000)
    })
  }

  function setProcessing() {
    if (state.value === 'submitting') {
      clearTimeout_()
      state.value = 'processing'
    }
  }

  function done() {
    state.value = 'idle'
    response.value = ''
    transcript.value = ''
    error.value = ''
  }

  return {
    state,
    transcript,
    response,
    error,
    triggerVoiceCommand,
    cancel,
    setProcessing,
    done,
  }
}
