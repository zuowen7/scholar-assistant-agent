import { describe, expect, it } from 'vitest'

import { computeSelectionToolbarPosition } from '../utils/selectionToolbarPosition'

const bounds = {
  viewportWidth: 900,
  viewportHeight: 700,
  toolbarWidth: 280,
  toolbarHeight: 41,
  containerLeft: 40,
  containerTop: 0,
}

describe('computeSelectionToolbarPosition', () => {
  it('anchors above a visible selection instead of pinning to the viewport top', () => {
    expect(computeSelectionToolbarPosition({ left: 420, top: 500, height: 30 }, bounds)).toEqual({
      visible: true,
      left: 320,
      top: 451,
      placement: 'above',
    })
  })

  it('moves below a selection when there is no room above it', () => {
    expect(computeSelectionToolbarPosition({ left: 240, top: 12, height: 30 }, bounds)).toEqual({
      visible: true,
      left: 140,
      top: 50,
      placement: 'below',
    })
  })

  it('clamps the toolbar inside both horizontal edges', () => {
    expect(computeSelectionToolbarPosition({ left: 0, top: 300, height: 30 }, bounds).left).toBe(8)
    expect(
      computeSelectionToolbarPosition(
        { left: 890, top: 300, height: 30 },
        { ...bounds, containerLeft: 0 },
      ).left,
    ).toBe(612)
  })

  it('hides when the active selection endpoint has scrolled outside the viewport', () => {
    expect(
      computeSelectionToolbarPosition({ left: 300, top: -60, height: 30 }, bounds).visible,
    ).toBe(false)
    expect(
      computeSelectionToolbarPosition({ left: 300, top: 710, height: 30 }, bounds).visible,
    ).toBe(false)
  })

  it('stays inside a short viewport when neither preferred side fully fits', () => {
    const position = computeSelectionToolbarPosition(
      { left: 160, top: 28, height: 30 },
      {
        viewportWidth: 320,
        viewportHeight: 80,
        toolbarWidth: 260,
        toolbarHeight: 56,
      },
    )

    expect(position.visible).toBe(true)
    expect(position.top).toBe(8)
    expect(position.left).toBe(30)
  })
})
