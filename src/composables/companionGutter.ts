/**
 * companionGutter — pure functions for computing Monaco glyph-margin decorations
 * from a Ledger and/or ReviewSession.
 *
 * Pure: no side effects, no imports from singleton composables. Easy to unit test.
 */
import type { Ledger, ReviewSession, Anchor, Promise, ReviewPoint } from '../types'

type MonacoNS = typeof import('monaco-editor')
type ITextModel = import('monaco-editor').editor.ITextModel
type IModelDeltaDecoration = import('monaco-editor').editor.IModelDeltaDecoration

/** Statuses that warrant a gutter glyph on the promise's source anchor. */
const GLYPH_STATUSES: Set<string> = new Set(['unpaid', 'mismatch', 'partial'])

/** Point statuses that should appear in the gutter (open only). */
const OPEN_STATUSES: Set<string> = new Set(['open'])

interface LineEntry {
  glyphClass: string
  hovers: string[]
}

function findAnchor(anchors: Anchor[], id: string): Anchor | undefined {
  return anchors.find(a => a.id === id)
}

/**
 * Compute all Monaco delta decorations for the current ledger + review session.
 * Decorations on the same line are merged into a single glyph with combined hover.
 */
export function computeCompanionDecorations(
  ledger: Ledger | null,
  review: ReviewSession | null,
  monaco: MonacoNS,
  model: ITextModel,
): IModelDeltaDecoration[] {
  // lineNumber → accumulated entry
  const lineMap = new Map<number, LineEntry>()

  function addToLine(lineNumber: number, glyphClass: string, hover: string) {
    if (lineMap.has(lineNumber)) {
      const entry = lineMap.get(lineNumber)!
      entry.hovers.push(hover)
      // keep the "most severe" class: error > warning > info
      const rank = (cls: string) =>
        cls.includes('unpaid') || cls.includes('mismatch') || cls.includes('fatal') ? 2
          : cls.includes('partial') || cls.includes('major') ? 1
          : 0
      if (rank(glyphClass) > rank(entry.glyphClass)) {
        entry.glyphClass = glyphClass
      }
    } else {
      lineMap.set(lineNumber, { glyphClass, hovers: [hover] })
    }
  }

  // ── Ledger promises ──────────────────────────────────────────────────────
  if (ledger) {
    for (const promise of ledger.promises) {
      if (!GLYPH_STATUSES.has(promise.status)) continue

      const anchor = findAnchor(ledger.anchors, promise.source_anchor_id)
      if (!anchor || anchor.status === 'lost' || anchor.char_start === null) continue

      const position = model.getPositionAt(anchor.char_start)
      const lineNumber = position.lineNumber
      const glyphClass = `arg-gutter-promise-${promise.status}`
      const hoverText = `⚠ ${promise.text}${promise.note ? ` — ${promise.note}` : ''}`
      addToLine(lineNumber, glyphClass, hoverText)
    }
  }

  // ── Review points ────────────────────────────────────────────────────────
  if (review) {
    for (const point of review.points) {
      if (!OPEN_STATUSES.has(point.status)) continue
      if (!point.anchor_id) continue

      const anchor = findAnchor(review.anchors, point.anchor_id)
      if (!anchor || anchor.status === 'lost' || anchor.char_start === null) continue

      const position = model.getPositionAt(anchor.char_start)
      const lineNumber = position.lineNumber
      const glyphClass = `arg-gutter-review-${point.severity}`
      addToLine(lineNumber, glyphClass, point.title)
    }
  }

  // ── Build decorations ────────────────────────────────────────────────────
  const decorations: IModelDeltaDecoration[] = []
  for (const [lineNumber, entry] of lineMap) {
    decorations.push({
      range: new monaco.Range(lineNumber, 1, lineNumber, 1),
      options: {
        glyphMarginClassName: entry.glyphClass,
        glyphMarginHoverMessage: {
          value: entry.hovers.join('\n\n'),
        },
        stickiness: 1, // NeverGrowsWhenTypingAtEdges
      },
    })
  }

  return decorations
}
