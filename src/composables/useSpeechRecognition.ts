import { ref } from 'vue'

type SpeechStatus = 'idle' | 'listening'

function getSpeechRecognition(): SpeechRecognition | null {
  const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
  if (!SR) return null
  return new SR()
}

export interface SpeechRecognitionOptions {
  onResult?: (text: string) => void
}

export function useSpeechRecognition(options?: SpeechRecognitionOptions) {
  const status = ref<SpeechStatus>('idle')
  const interimText = ref('')
  const error = ref('')
  let recognition: SpeechRecognition | null = null
  let finalText = ''
  let lastProcessedFinal = -1

  function start(lang = 'zh-CN') {
    if (status.value === 'listening') return
    error.value = ''
    interimText.value = ''
    finalText = ''
    lastProcessedFinal = -1

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
      let latestInterim = ''
      for (let i = 0; i < e.results.length; i++) {
        if (e.results[i].isFinal && i > lastProcessedFinal) {
          finalText += e.results[i][0].transcript
          lastProcessedFinal = i
        } else if (!e.results[i].isFinal) {
          latestInterim = e.results[i][0].transcript
        }
      }
      // Filter phantom interim: if interim is just a duplicate/refinement of
      // accumulated final text, discard it (some browsers re-emit finalized audio)
      let text = finalText + latestInterim
      if (latestInterim && finalText) {
        const ci = latestInterim.replace(/[^\w一-鿿]/g, '').toLowerCase()
        const cf = finalText.replace(/[^\w一-鿿]/g, '').toLowerCase()
        console.log('[Speech] phantom check: final="%s" interim="%s" | ci="%s" cf="%s" end=%s inc=%s',
          finalText.slice(-20), latestInterim.slice(-20), ci, cf, cf.endsWith(ci), cf.includes(ci))
        if (cf.endsWith(ci) || cf.includes(ci)) {
          text = finalText  // interim is duplicate, use final only
        }
      }
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
