import { describe, expect, it } from 'vitest'

import { computeInlineDiffOverlayPosition } from '../utils/inlineDiffOverlayPosition'

describe('computeInlineDiffOverlayPosition', () => {
  it('keeps an inline diff card inside the editor near the document bottom', () => {
    expect(
      computeInlineDiffOverlayPosition({
        anchorTop: 720,
        viewportHeight: 800,
        overlayHeight: 360,
      }),
    ).toEqual({
      top: 428,
      maxHeight: 360,
    })
  })

  it('preserves the line anchor when the card already fits below it', () => {
    expect(
      computeInlineDiffOverlayPosition({
        anchorTop: 200,
        viewportHeight: 800,
        overlayHeight: 140,
      }),
    ).toEqual({
      top: 200,
      maxHeight: 360,
    })
  })

  it('shrinks the card height budget in a short editor viewport', () => {
    expect(
      computeInlineDiffOverlayPosition({
        anchorTop: 180,
        viewportHeight: 240,
        overlayHeight: 360,
      }),
    ).toEqual({
      top: 12,
      maxHeight: 216,
    })
  })
})
