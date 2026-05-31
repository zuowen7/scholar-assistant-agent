import { ref } from 'vue'

type SpeechStatus = 'idle' | 'listening'

function getSpeechRecognition(): SpeechRecognition | null {
  const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
  if (!SR) return null
  return new SR()
}

export interface SpeechRecognitionOptions {
  onResult?: (text: string) => void
  onEnd?: () => void
}

function normalize(s: string) {
  return s.replace(/[^\w一-鿿]/g, '').toLowerCase()
}

// Words that unambiguously start a NEW sentence after a pause.
// Pronouns (我/你/他/它/这/那) are NOT included — they often continue the same sentence.
const SENTENCE_STARTERS_RE = /^(但是|然而|所以|因此|另外|首先|其次|最后|总之|不过|而且|此外|可是|然后|接着|当然|确实|其实|显然|终于|突然|忽然|偶尔|经常|一直|如果|虽然|因为|由于|为了|关于|根据|按照|通过|经过|比如|例如|除了|包括|尤其|特别|最|更|比|越|[A-Z])/

/**
 * Join a new utterance onto accumulated text, avoiding premature Chrome-added
 * punctuation when the speaker just paused (not ended the sentence).
 */
function joinUtterances(prev: string, next: string): string {
  if (!prev) return next
  // Chrome adds sentence-ending punctuation on pause — strip it if the next
  // utterance looks like a continuation rather than a new sentence.
  const stripped = prev.replace(/[。！？.!?]+$/, '')
  if (stripped === prev) {
    // No trailing punctuation to worry about — just append
    return prev + ' ' + next
  }
  const trailing = prev.slice(stripped.length)
  // Detect if `next` starts a new sentence:
  // - English capital letter or Chinese sentence-starter → keep the punctuation
  // - Otherwise → continuation, replace punctuation with a comma (Chinese) or nothing (English)
  if (SENTENCE_STARTERS_RE.test(next.trimStart())) {
    return prev + ' ' + next
  }
  // Continuation — join with a comma for Chinese, space for English
  const isCJK = /[一-鿿]/.test(next)
  const sep = isCJK ? '，' : ' '
  return stripped + sep + next
}

/** Detect and remove internal duplication within a transcript (WebView bug workaround). */
function deduplicateWithin(text: string): string {
  const n = text.length
  if (n < 3) return text
  const normText = normalize(text)
  if (!normText) return text
  // Find the best split point where the two halves have significant overlap
  let bestSplit = -1
  let bestOverlap = 0
  for (let i = Math.floor(n / 3); i <= Math.floor(n * 2 / 3); i++) {
    const normA = normalize(text.slice(0, i))
    const normB = normalize(text.slice(i))
    if (!normA || !normB) continue
    // Measure overlap: what fraction of the shorter string is contained in the longer
    const shorter = normA.length < normB.length ? normA : normB
    const longer = normA.length < normB.length ? normB : normA
    if (longer.includes(shorter)) {
      const overlap = shorter.length / longer.length
      if (overlap > bestOverlap) {
        bestOverlap = overlap
        bestSplit = i
      }
    }
  }
  // If >60% of one half is contained in the other, it's likely a duplication
  if (bestOverlap > 0.6 && bestSplit > 0) {
    const first = text.slice(0, bestSplit)
    const second = text.slice(bestSplit)
    // Keep the longer version
    return first.length >= second.length ? first : second
  }
  return text
}

export function useSpeechRecognition(options?: SpeechRecognitionOptions) {
  const status = ref<SpeechStatus>('idle')
  const interimText = ref('')
  const error = ref('')
  let recognition: SpeechRecognition | null = null
  let finalText = ''
  let lastEmitted = ''

  function start(lang = 'zh-CN') {
    if (status.value === 'listening') return
    error.value = ''
    interimText.value = ''
    finalText = ''
    lastEmitted = ''

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
    sr.onend = () => { status.value = 'idle'; options?.onEnd?.() }
    sr.onerror = (e) => {
      if (e.error !== 'no-speech' && e.error !== 'aborted') {
        error.value = e.error
      }
      status.value = 'idle'
    }

    sr.onresult = (e) => {
      let latestInterim = ''

      for (let i = 0; i < e.results.length; i++) {
        if (e.results[i].isFinal) {
          const transcript = e.results[i][0].transcript
          const norm = normalize(transcript)
          if (!norm) continue

          const normFinal = normalize(finalText)

          // Already contained in accumulated finals → echo, skip
          if (normFinal.includes(norm)) continue
          // New transcript is a superset — only replace if the NEW part is
          // genuinely different (not a repetition of what's already in finalText)
          if (norm.includes(normFinal)) {
            const newPart = norm.slice(normFinal.length)
            if (newPart.length < 2 || normFinal.includes(newPart)) {
              // New part is empty or a repetition of existing content → echo, skip
              continue
            }
            finalText = transcript
            continue
          }
          // Distinct utterance — merge with smart punctuation handling
          finalText = joinUtterances(finalText, transcript)
        } else {
          latestInterim = e.results[i][0].transcript
        }
      }

      let text = finalText + latestInterim

      // Interim-final dedup: if the interim overlaps substantially with finalText,
      // use only finalText (the interim is either an incomplete echo or a garbled
      // superset — both are unreliable compared to the already-finalized result).
      if (latestInterim && finalText) {
        const normInterim = normalize(latestInterim)
        const normFinal = normalize(finalText)
        if (normFinal.includes(normInterim) || normInterim.includes(normFinal)) {
          text = finalText
        }
      }

      // Post-process: detect internal duplication within the transcript itself
      // (some WebView speech engines produce "A。AA。" from a single utterance)
      text = deduplicateWithin(text)

      interimText.value = text
      if (text !== lastEmitted) {
        lastEmitted = text
        options?.onResult?.(text)
      }
    }

    sr.start()
  }

  function stop(): string {
    const text = interimText.value
    if (recognition) {
      recognition.onresult = null
      recognition.stop()
    }
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
