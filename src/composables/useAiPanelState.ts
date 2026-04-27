import { ref } from 'vue'

export interface AiPanelMsg {
  id: string
  role: 'user' | 'assistant'
  content: string
  thinking?: string
  isStreaming?: boolean
}

// Module-level singleton — survives AiPanel unmount/remount when EditorLayout is v-if'd out
export const aiMessages = ref<AiPanelMsg[]>([])
export const aiStreaming = ref(false)
export const aiStreamContent = ref('')
export const aiThinkingText = ref('')
export const aiAbortCtrl = ref<AbortController | null>(null)
