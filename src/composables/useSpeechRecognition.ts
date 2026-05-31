import { ref } from 'vue'

type SpeechStatus = 'idle' | 'listening'

function getSpeechRecognition(): SpeechRecognition | null {
  const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
  if (!SR) return null
  return new SR()
}

export interface SpeechRecognitionOptions {
  /** Fires on every result update (interim + final accumulated text) */
  onResult?: (text: string) => void
}

export function useSpeechRecognition(options?: SpeechRecognitionOptions) {
  const status = ref<SpeechStatus>('idle')
  const interimText = ref('')
  const error = ref('')
  let recognition: SpeechRecognition | null = null

  function start(lang = 'zh-CN') {
    if (status.value === 'listening') return
    error.value = ''
    interimText.value = ''

    const sr = getSpeechRecognition()
    if (!sr) {
      error.value = 'Speech recognition not supported'
      return
    }

    recognition = sr
    sr.continuous = true
    sr.interimResults = true
    sr.lang = lang

    sr.onstart = () => { status.value = 'listening' }
    sr.onend = () => { status.value = 'idle' }
    sr.onerror = (e) => {
      if (e.error !== 'no-speech' && e.error !== 'aborted') {
        error.value = e.error
      }
      status.value = 'idle'
    }

    sr.onresult = (e) => {
      let final = ''
      let interim = ''
      for (let i = 0; i < e.results.length; i++) {
        const r = e.results[i]
        if (r.isFinal) {
          final += r[0].transcript
        } else {
          interim += r[0].transcript
        }
      }
      const text = final + interim
      interimText.value = text
      options?.onResult?.(text)
    }

    sr.start()
  }

  function stop(): string {
    const text = interimText.value
    recognition?.stop()
    recognition = null
    status.value = 'idle'
    interimText.value = ''
    return text
  }

  function toggle(lang = 'zh-CN') {
    if (status.value === 'listening') {
      stop()
    } else {
      start(lang)
    }
  }

  const isSupported = !!((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition)

  return { status, interimText, error, isSupported, start, stop, toggle }
}
