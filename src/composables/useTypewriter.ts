import { ref, watch, onUnmounted } from 'vue'

/**
 * Typewriter effect for AiPanel streaming results.
 * Renders characters progressively at a configurable rate (default ~30 chars/sec).
 */
export function useTypewriter(speed = 30) {
  const source = ref('')
  const display = ref('')
  const typing = ref(false)
  let timer: ReturnType<typeof setTimeout> | null = null
  let cursor = 0

  function tick() {
    if (cursor < source.value.length) {
      const chunkSize = Math.max(1, Math.ceil(speed / 20))
      cursor = Math.min(cursor + chunkSize, source.value.length)
      display.value = source.value.slice(0, cursor)
      const delay = Math.max(8, Math.round(1000 / speed))
      timer = setTimeout(tick, delay)
    } else {
      typing.value = false
    }
  }

  function reset() {
    if (timer) { clearTimeout(timer); timer = null }
    cursor = 0
    display.value = ''
    typing.value = false
  }

  watch(source, (newVal, oldVal) => {
    // If content was prepended or changed drastically, show immediately
    if (newVal.length < oldVal.length) {
      reset()
      display.value = newVal
      cursor = newVal.length
      return
    }

    // Start typing if not already
    if (!typing.value && cursor < newVal.length) {
      typing.value = true
      tick()
    } else if (typing.value) {
      // Continue — source keeps growing while we type
    }
  })

  onUnmounted(() => {
    if (timer) clearTimeout(timer)
  })

  /** Feed new content (append or replace) */
  function feed(text: string) {
    source.value = text
  }

  /** Skip to end immediately */
  function finish() {
    if (timer) { clearTimeout(timer); timer = null }
    cursor = source.value.length
    display.value = source.value
    typing.value = false
  }

  return { display, typing, feed, finish, reset }
}
