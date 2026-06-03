import { ref } from 'vue'

type SpeechStatus = 'idle' | 'listening'

declare class SpeechRecognition extends EventTarget {
  continuous: boolean; interimResults: boolean; lang: string
  start(): void; stop(): void; abort(): void
  onstart: ((ev: Event) => void) | null
  onend: ((ev: Event) => void) | null
  onerror: ((ev: SpeechRecognitionErrorEvent) => void) | null
  onresult: ((ev: SpeechRecognitionEvent) => void) | null
}
declare class SpeechRecognitionErrorEvent extends Event { error: string; message: string }
declare class SpeechRecognitionEvent extends Event {
  resultIndex: number; results: SpeechRecognitionResultList
}
declare class SpeechRecognitionResultList { readonly length: number; [index: number]: SpeechRecognitionResult }
declare class SpeechRecognitionResult { readonly isFinal: boolean; readonly length: number; [index: number]: SpeechRecognitionAlternative }
declare class SpeechRecognitionAlternative { transcript: string; confidence: number }

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

function commonPrefixLen(a: string, b: string): number {
  const len = Math.min(a.length, b.length)
  for (let i = 0; i < len; i++) {
    if (a[i] !== b[i]) return i
  }
  return len
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
  let processedUpTo = -1
  let utterances: string[] = []

  function start(lang = 'zh-CN') {
    if (status.value === 'listening') return
    error.value = ''
    interimText.value = ''
    finalText = ''
    lastEmitted = ''
    processedUpTo = -1
    utterances = []

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
    sr.onerror = (e: SpeechRecognitionErrorEvent) => {
      if (e.error !== 'no-speech' && e.error !== 'aborted') {
        error.value = e.error
      }
      status.value = 'idle'
    }

    sr.onresult = (e: SpeechRecognitionEvent) => {
      let latestInterim = ''

      for (let i = 0; i < e.results.length; i++) {
        if (e.results[i].isFinal) {
          if (i <= processedUpTo) continue
          processedUpTo = i
          const transcript = e.results[i][0].transcript
          const norm = normalize(transcript)
          if (!norm) continue

          const normFinal = normalize(finalText)

          // Already contained in accumulated finals → echo, skip
          if (normFinal.includes(norm)) continue

          // Superset: new result contains all accumulated text
          if (norm.includes(normFinal) && normFinal.length > 0) {
            finalText = transcript
            utterances = [transcript]
            continue
          }

          // Chrome continuous mode sometimes re-recognizes earlier audio and
          // produces a new result whose beginning overlaps with a previous
          // utterance. Detect this by checking the prefix of the new result
          // against each previous individual utterance.
          let reincluded = false
          for (const prev of utterances) {
            const prevNorm = normalize(prev)
            if (prevNorm.length < 4) continue
            const overlap = commonPrefixLen(norm, prevNorm)
            if (overlap > prevNorm.length * 0.5) {
              // Re-inclusion detected — extract only the genuinely new suffix
              let counted = 0
              let splitAt = transcript.length
              for (let ci = 0; ci < transcript.length; ci++) {
                if (/[\w一-鿿]/.test(transcript[ci])) counted++
                if (counted >= prevNorm.length) { splitAt = ci + 1; break }
              }
              const newOnly = transcript.slice(splitAt).trim()
              if (newOnly) {
                finalText = joinUtterances(finalText, newOnly)
              }
              reincluded = true
              break
            }
          }
          if (reincluded) continue

          // Distinct utterance — merge with smart punctuation handling
          finalText = joinUtterances(finalText, transcript)
          utterances.push(transcript)
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
    finalText = ''
    lastEmitted = ''
    processedUpTo = -1
    utterances = []
    return text
  }

  /** Reset accumulated text without stopping recognition. */
  function resetAccumulated() {
    finalText = ''
    lastEmitted = ''
    interimText.value = ''
    utterances = []
    // Keep processedUpTo — Chrome's results array is unchanged
  }

  function toggle(lang = 'zh-CN') {
    if (status.value === 'listening') {
      stop()
    } else {
      start(lang)
    }
  }

  const isSupported = !!((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition)

  return { status, interimText, error, isSupported, start, stop, toggle, resetAccumulated }
}
