import { ref } from 'vue'
import { useSpeechRecognition } from './useSpeechRecognition'
import { logger } from '../utils/logger'
import { i18n } from '../i18n'
import { useToast } from './useToast'
import { getCurrentWindow } from '@tauri-apps/api/window'

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

export type VoiceCommandState = 'idle' | 'activating' | 'listening' | 'submitting' | 'processing' | 'result' | 'error'

// ── Module-level singleton state ───────────────────────────────────────

const state = ref<VoiceCommandState>('idle')
const transcript = ref('')
const response = ref('')
const error = ref('')

let timeoutHandle: ReturnType<typeof setTimeout> | null = null
let silenceHandle: ReturnType<typeof setTimeout> | null = null
let resultHandle: ReturnType<typeof setTimeout> | null = null
let speechStarted = false

function clearTimeout_() {
  if (timeoutHandle !== null) { clearTimeout(timeoutHandle); timeoutHandle = null }
  if (silenceHandle !== null) { clearTimeout(silenceHandle); silenceHandle = null }
  if (resultHandle !== null) { clearTimeout(resultHandle); resultHandle = null }
}

function stopSpeech() {
  if (!speechStarted) return
  speech.stop()
  speechStarted = false
}

function submit() {
  clearTimeout_()
  const text = transcript.value.trim()
  if (!text) { cancel(); return }
  stopSpeech()
  state.value = 'submitting'
  logger.debug('[voice] submitting:', text)
  window.dispatchEvent(new CustomEvent('voice-command-submit', {
    detail: { text },
  }))
}

function cancel() {
  clearTimeout_()
  stopSpeech()
  state.value = 'idle'
  transcript.value = ''
  response.value = ''
  error.value = ''
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
  onError(message: string) {
    if (state.value === 'listening' || state.value === 'activating') {
      fail(describeSpeechError(message))
    }
  },
})

function describeSpeechError(message: string) {
  const normalized = message.trim().toLowerCase()
  if (normalized === 'no-speech') return i18n.global.t('voice.noSpeech')
  if (normalized === 'not-allowed' || normalized === 'service-not-allowed') return i18n.global.t('voice.permissionDenied')
  if (normalized === 'audio-capture') return i18n.global.t('voice.microphoneUnavailable')
  if (normalized === 'network') return i18n.global.t('voice.networkError')
  return message || i18n.global.t('voice.startFailed')
}

function fail(message: string) {
  clearTimeout_()
  stopSpeech()
  error.value = message
  state.value = 'error'
  // Show a user-visible toast so the user knows why voice failed
  // (without this, the error is only in composable state — invisible to the user)
  try { useToast().pushError(message) } catch { /* ignore if no toast context */ }
}

export function useVoiceCommand() {
  function triggerVoiceCommand() {
    logger.debug('[voice] triggerVoiceCommand, state=', state.value)
    if (state.value === 'error' || state.value === 'result') {
      cancel()
    } else if (state.value !== 'idle') {
      cancel()
      return
    }

    if (!speech.isSupported) {
      fail(i18n.global.t('voice.notSupported'))
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
      if (!speech.start(lang)) {
        speechStarted = false
        fail(describeSpeechError(speech.error.value))
        return
      }

      // 10s absolute timeout — no speech at all
      timeoutHandle = setTimeout(() => {
        if (state.value === 'listening') {
          fail(i18n.global.t('voice.noSpeech'))
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
    clearTimeout_()
    stopSpeech()
    state.value = 'idle'
    response.value = ''
    transcript.value = ''
    error.value = ''
  }

  function finish(message = '') {
    clearTimeout_()
    stopSpeech()
    error.value = ''
    response.value = message
    state.value = 'result'
    resultHandle = setTimeout(done, 2200)
  }

  return {
    state,
    transcript,
    response,
    error,
    triggerVoiceCommand,
    cancel,
    setProcessing,
    finish,
    fail,
    done,
  }
}
