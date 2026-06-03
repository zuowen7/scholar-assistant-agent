export interface VoiceCommandDef {
  id: string
  label: { zh: string; en: string }
  patternsZh: (string | RegExp)[]
  patternsEn: (string | RegExp)[]
  /** Minimum confidence threshold (0-1, default 0.25) */
  threshold?: number
  /** Higher priority = checked first (default 0) */
  priority?: number
  handler: (params: Record<string, string>, rawText: string) => Promise<void>
}

export interface VoiceCommandMatch {
  commandId: string
  label: { zh: string; en: string }
  score: number
  params: Record<string, string>
}

export interface VoiceCommandResult {
  type: 'command' | 'chat'
  commandId?: string
  label?: { zh: string; en: string }
  success: boolean
  error?: string
  text?: string
}
