/**
 * AI Inline Completions — fetch logic extracted for testability.
 * Used by MonacoEditor.vue's manual ghost text system.
 */

export interface CompletionModel {
  getLineContent(lineNumber: number): string
  getValueInRange(range: { startLineNumber: number; startColumn: number; endLineNumber: number; endColumn: number }): string
  getLineMaxColumn(lineNumber: number): number
}

export interface CompletionPosition {
  lineNumber: number
  column: number
}

export interface CompletionResult {
  completion: string
  position: CompletionPosition
}

export interface CompletionOptions {
  apiBase: string
}

const CONTEXT_LINES = 15
const MIN_CONTEXT_CHARS = 10
const MAX_TOKENS = 200
const TIMEOUT_MS = 30_000

export function buildContext(model: CompletionModel, position: CompletionPosition): string | null {
  const maxCol = model.getLineMaxColumn(position.lineNumber)
  if (position.column < maxCol) return null

  const startLine = Math.max(1, position.lineNumber - CONTEXT_LINES)
  const ctx = model.getValueInRange({
    startLineNumber: startLine,
    startColumn: 1,
    endLineNumber: position.lineNumber,
    endColumn: position.column,
  })
  if (ctx.trim().length < MIN_CONTEXT_CHARS) return null
  return ctx
}

export async function fetchCompletion(
  ctx: string,
  position: CompletionPosition,
  options: CompletionOptions,
  signal?: AbortSignal,
): Promise<CompletionResult | null> {
  try {
    const ctrl = new AbortController()
    const timeout = setTimeout(() => ctrl.abort(), TIMEOUT_MS)
    // Combine external signal with our timeout
    if (signal) {
      signal.addEventListener('abort', () => ctrl.abort())
    }

    const resp = await fetch(`${options.apiBase}/api/complete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ context: ctx, max_tokens: MAX_TOKENS }),
      signal: ctrl.signal,
    })
    clearTimeout(timeout)
    if (!resp.ok) return null
    const data = await resp.json() as { completion?: string }
    const completion = (data.completion || '').trim()
    if (!completion) return null

    return { completion, position }
  } catch {
    return null
  }
}

// Legacy interface for tests
export interface CompletionItem {
  insertText: string
  range: { startLineNumber: number; startColumn: number; endLineNumber: number; endColumn: number }
}

export interface CompletionOptionsLegacy {
  apiBase: string
  paletteOpen: boolean
}

export async function provideAICompletion(
  model: CompletionModel,
  position: CompletionPosition,
  options: CompletionOptionsLegacy,
): Promise<{ items: CompletionItem[] }> {
  if (options.paletteOpen) return { items: [] }

  const ctx = buildContext(model, position)
  if (!ctx) return { items: [] }

  const result = await fetchCompletion(ctx, position, { apiBase: options.apiBase })
  if (!result) return { items: [] }

  return {
    items: [{
      insertText: result.completion,
      range: {
        startLineNumber: position.lineNumber,
        startColumn: position.column,
        endLineNumber: position.lineNumber,
        endColumn: position.column,
      },
    }],
  }
}
