export interface SelectionAnchorPosition {
  left: number
  top: number
  height: number
}

export interface SelectionToolbarBounds {
  viewportWidth: number
  viewportHeight: number
  toolbarWidth: number
  toolbarHeight: number
  containerLeft?: number
  containerTop?: number
  margin?: number
  gap?: number
}

export interface SelectionToolbarPosition {
  visible: boolean
  left: number
  top: number
  placement: 'above' | 'below'
}

/**
 * Positions the transient selection toolbar inside the Monaco wrapper.
 * The anchor coordinates are Monaco-local; container offsets translate them
 * into wrapper coordinates when document mode centers the editor canvas.
 */
export function computeSelectionToolbarPosition(
  anchor: SelectionAnchorPosition | null,
  bounds: SelectionToolbarBounds,
): SelectionToolbarPosition {
  const margin = bounds.margin ?? 8
  const gap = bounds.gap ?? 8
  const containerLeft = bounds.containerLeft ?? 0
  const containerTop = bounds.containerTop ?? 0
  const hidden: SelectionToolbarPosition = {
    visible: false,
    left: margin,
    top: margin,
    placement: 'above',
  }

  if (
    !anchor ||
    bounds.viewportWidth <= 0 ||
    bounds.viewportHeight <= 0 ||
    bounds.toolbarWidth <= 0 ||
    bounds.toolbarHeight <= 0
  ) {
    return hidden
  }

  const anchorTop = containerTop + anchor.top
  const anchorBottom = anchorTop + anchor.height
  if (anchorBottom < 0 || anchorTop > bounds.viewportHeight) return hidden

  const maxLeft = Math.max(margin, bounds.viewportWidth - bounds.toolbarWidth - margin)
  const unclampedLeft = containerLeft + anchor.left - bounds.toolbarWidth / 2
  const left = Math.min(Math.max(unclampedLeft, margin), maxLeft)

  const aboveTop = anchorTop - bounds.toolbarHeight - gap
  const belowTop = anchorBottom + gap
  if (aboveTop >= margin) {
    return { visible: true, left, top: aboveTop, placement: 'above' }
  }
  if (belowTop + bounds.toolbarHeight <= bounds.viewportHeight - margin) {
    return { visible: true, left, top: belowTop, placement: 'below' }
  }

  const maxTop = Math.max(margin, bounds.viewportHeight - bounds.toolbarHeight - margin)
  const top = Math.min(Math.max(aboveTop, margin), maxTop)
  return { visible: true, left, top, placement: top < anchorTop ? 'above' : 'below' }
}
