/**
 * Runtime API response validators (M12).
 * Type-guard based — no external dependency required.
 * Covers /api/translate (upload), /api/translate/:id/stream event payloads,
 * and /api/agent/v2/chat.
 */

// ── Generic helpers ──────────────────────────────────────────────────────────

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
}

function hasString(obj: Record<string, unknown>, key: string): boolean {
  return typeof obj[key] === 'string'
}

function hasNumber(obj: Record<string, unknown>, key: string): boolean {
  return typeof obj[key] === 'number'
}

// ── /api/translate (upload response) ────────────────────────────────────────

export interface TranslateUploadResponse {
  task_id: string
}

export function validateTranslateUpload(v: unknown): TranslateUploadResponse {
  if (!isObject(v) || !hasString(v, 'task_id')) {
    throw new TypeError(`Invalid /api/translate response: ${JSON.stringify(v)}`)
  }
  return { task_id: v.task_id as string }
}

// ── /api/translate/:id/stream SSE progress event ────────────────────────────

export interface TranslateProgressPayload {
  step: number
  total: number
  message: string
}

export function parseTranslateProgress(v: unknown): TranslateProgressPayload | null {
  if (!isObject(v)) return null
  if (!hasNumber(v, 'step') || !hasNumber(v, 'total')) return null
  return {
    step: v.step as number,
    total: v.total as number,
    message: typeof v.message === 'string' ? v.message : '',
  }
}

// ── /api/agent/v2/chat (stream start) ───────────────────────────────────────

export interface AgentChatStartResponse {
  session_id: string
}

export function validateAgentChatStart(v: unknown): AgentChatStartResponse {
  if (!isObject(v) || !hasString(v, 'session_id')) {
    throw new TypeError(`Invalid /api/agent/v2/chat response: ${JSON.stringify(v)}`)
  }
  return { session_id: v.session_id as string }
}

// ── Generic API error shape from backend ────────────────────────────────────

export interface ApiError {
  detail?: string
  error?: string | { code?: string; message?: string }
  message?: string
}

export function extractApiErrorMessage(v: unknown): string {
  if (!isObject(v)) return String(v)
  if (hasString(v, 'detail')) return v.detail as string
  if (hasString(v, 'message')) return v.message as string
  const err = v['error']
  if (typeof err === 'string') return err
  if (isObject(err) && hasString(err, 'message')) return err.message as string
  return JSON.stringify(v)
}
