import { ref, watch } from 'vue'
import { isSpeechBusy, speechBusyCount } from './useSpeechBusy'

function getWakeWordPhrase(): string {
  try {
    const raw = localStorage.getItem('voice-settings')
    if (raw) {
      const s = JSON.parse(raw)
      if (s.wakeWordPhrase) return s.wakeWordPhrase
    }
  } catch { /* ignore */ }
  return '小研'
}

// Common homophones for wake word characters — speech recognition often
// picks different characters for the same sound
const HOMOPHONE_GROUPS: Record<string, string[]> = {
  '研': ['研', '严', '言', '岩', '颜', '盐', '炎', '延'],
  '小': ['小', '晓', '筱'],
  '你': ['你', '尼', '拟'],
  '好': ['好', '号'],
  '贾': ['贾', '假', '甲', '加', '家', '佳'],
  '维': ['维', '围', '唯', '微', '韦', '威'],
  '斯': ['斯', '丝', '司', '思', '私', '撕'],
}

function buildVariants(phrase: string): string[] {
  // Generate all homophone variants of the phrase
  // e.g. "小研" → ["小研", "小严", "小言", ...]
  if (!phrase) return []

  let variants = ['']
  for (const char of phrase) {
    const group = HOMOPHONE_GROUPS[char]
    if (group) {
      variants = variants.flatMap(v => group.map(g => v + g))
    } else {
      variants = variants.map(v => v + char)
    }
  }
  return variants
}

function matchWakeWord(text: string): boolean {
  const phrase = getWakeWordPhrase()
  // Exact match
  if (text.includes(phrase)) return true
  // Homophone match
  const variants = buildVariants(phrase)
  for (const v of variants) {
    if (v !== phrase && text.includes(v)) return true
  }
  return false
}

/**
 * Wake word detection using Web Speech API in continuous mode.
 * Listens for the configured wake word phrase (default "小研").
 * When detected, calls onWakeWord().
 */
export function useWakeWord(onWakeWord: () => void) {
  const active = ref(false)
  const error = ref('')

  let sr: any = null
  let restarting = false
  let restartTimer: ReturnType<typeof setTimeout> | null = null
  let cooldown = false

  const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition

  async function startWakeWord() {
    if (active.value) return
    if (!SpeechRecognition) {
      error.value = '浏览器不支持语音识别'
      return
    }

    try {
      sr = new SpeechRecognition()
      sr.continuous = true
      sr.interimResults = true
      sr.lang = 'zh-CN'
      sr.maxAlternatives = 3

      sr.onresult = (event: any) => {
        // Don't trigger while dictation is active or during cooldown
        if (isSpeechBusy() || cooldown) return
        for (let i = event.resultIndex; i < event.results.length; i++) {
          for (let j = 0; j < event.results[i].length; j++) {
            const text = event.results[i][j].transcript.toLowerCase()
            console.log('[wake-word] heard:', text)
            if (matchWakeWord(text)) {
              console.log('[wake-word] MATCH:', text)
              // Stop listening immediately to prevent re-triggering
              try { sr?.stop() } catch { /* ignore */ }
              cooldown = true
              onWakeWord()
              // Cooldown: ignore matches for 5 seconds
              setTimeout(() => { cooldown = false }, 5000)
              return
            }
          }
        }
      }

      sr.onerror = (e: any) => {
        // Don't restart while paused for dictation
        if (pausedByDictation) return
        // 'no-speech' and 'aborted' are normal — restart
        if (e.error === 'no-speech' || e.error === 'aborted') {
          scheduleRestart()
          return
        }
        console.warn('[wake-word] error:', e.error)
        // For network/aborted errors, try restarting
        if (!restarting) scheduleRestart()
      }

      sr.onend = () => {
        // Don't restart while paused for dictation
        if (pausedByDictation) return
        // Speech recognition ended — auto-restart to keep listening
        if (active.value) scheduleRestart()
      }

      sr.start()
      active.value = true
      console.log('[wake-word] started, listening for:', getWakeWordPhrase())
    } catch (e: any) {
      error.value = e.message || '无法启动语音识别'
      console.warn('[wake-word] start failed:', e)
    }
  }

  function scheduleRestart() {
    if (restartTimer || !active.value) return
    restarting = true
    restartTimer = setTimeout(() => {
      restartTimer = null
      restarting = false
      if (!active.value) return
      try {
        sr?.start()
      } catch {
        // Already started or destroyed, ignore
      }
    }, 300)
  }

  function stopWakeWord() {
    if (restartTimer) { clearTimeout(restartTimer); restartTimer = null }
    restarting = false
    pausedByDictation = false
    if (sr) {
      try { sr.stop() } catch { /* ignore */ }
      sr = null
    }
    active.value = false
  }

  // Auto-pause on blur/hidden, resume on focus
  function onBlur() {
    if (active.value) {
      try { sr?.stop() } catch { /* ignore */ }
    }
  }
  function onFocus() {
    if (active.value && !pausedByDictation) {
      try { sr?.start() } catch { /* ignore */ }
    }
  }
  function onVisibility() {
    if (document.hidden) onBlur()
    else onFocus()
  }

  // Pause/resume SR when dictation (mic buttons) starts/stops.
  // Only one SpeechRecognition can be active at a time on most platforms.
  // Use flush:'sync' so the wake word SR is stopped BEFORE the dictation SR starts.
  let pausedByDictation = false
  watch(speechBusyCount, (count) => {
    if (count > 0 && active.value && !pausedByDictation) {
      pausedByDictation = true
      try { sr?.stop() } catch { /* ignore */ }
    } else if (count === 0 && pausedByDictation) {
      pausedByDictation = false
      if (active.value) {
        try { sr?.start() } catch { /* ignore */ }
      }
    }
  }, { flush: 'sync' })

  // Register listeners once (they check active.value)
  window.addEventListener('blur', onBlur)
  window.addEventListener('focus', onFocus)
  document.addEventListener('visibilitychange', onVisibility)

  return {
    active,
    error,
    startWakeWord,
    stopWakeWord,
  }
}
