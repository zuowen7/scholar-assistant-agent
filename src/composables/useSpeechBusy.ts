import { ref } from 'vue'

// Shared flag: when true, some speech activity (dictation, etc.) is in progress.
// Wake word detection should pause to avoid conflicts.
export const speechBusyCount = ref(0)

export function isSpeechBusy(): boolean {
  return speechBusyCount.value > 0
}

export function setSpeechBusy(busy: boolean) {
  if (busy) {
    speechBusyCount.value++
  } else {
    speechBusyCount.value = Math.max(0, speechBusyCount.value - 1)
  }
}
