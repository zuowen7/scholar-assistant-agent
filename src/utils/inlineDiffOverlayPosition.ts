export interface InlineDiffOverlayPositionInput {
  anchorTop: number
  viewportHeight: number
  overlayHeight: number
  edgePadding?: number
  maxOverlayHeight?: number
}

export interface InlineDiffOverlayPosition {
  top: number
  maxHeight: number
}

function finiteOrZero(value: number): number {
  return Number.isFinite(value) ? value : 0
}

export function computeInlineDiffOverlayPosition({
  anchorTop,
  viewportHeight,
  overlayHeight,
  edgePadding = 12,
  maxOverlayHeight = 360,
}: InlineDiffOverlayPositionInput): InlineDiffOverlayPosition {
  const viewport = Math.max(0, finiteOrZero(viewportHeight))
  const padding = Math.min(Math.max(0, finiteOrZero(edgePadding)), viewport / 2)
  const availableHeight = Math.max(0, viewport - padding * 2)
  const maxHeight = Math.min(Math.max(0, finiteOrZero(maxOverlayHeight)), availableHeight)
  const renderedHeight = Math.min(Math.max(0, finiteOrZero(overlayHeight)), maxHeight)
  const maxTop = Math.max(padding, viewport - padding - renderedHeight)
  const top = Math.min(Math.max(finiteOrZero(anchorTop), padding), maxTop)

  return { top, maxHeight }
}
