import { describe, expect, it, vi } from 'vitest'

import { addInlineDiffViewZone } from '../utils/inlineDiffViewZone'

describe('addInlineDiffViewZone', () => {
  it('reserves editor space and keeps long diff content inside a scrollable card', () => {
    let capturedZone: {
      afterLineNumber: number
      heightInPx: number
      domNode: HTMLElement
    } | null = null
    const removeZone = vi.fn()
    const editor = {
      changeViewZones: vi.fn(
        (
          callback: (accessor: {
            addZone: (zone: typeof capturedZone) => string
            removeZone: (id: string) => void
          }) => void,
        ) => {
          callback({
            addZone: (zone) => {
              capturedZone = zone
              return 'zone_1'
            },
            removeZone,
          })
        },
      ),
    }
    const onAccept = vi.fn()
    const onReject = vi.fn()
    const longText = Array.from({ length: 40 }, (_, index) => `第 ${index + 1} 行建议`).join('\n')

    const view = addInlineDiffViewZone(editor, {
      afterLineNumber: 12,
      newText: longText,
      title: '建议修改',
      acceptLabel: '接受',
      rejectLabel: '拒绝',
      onAccept,
      onReject,
    })

    expect(view.id).toBe('zone_1')
    expect(capturedZone).not.toBeNull()
    expect(capturedZone!.afterLineNumber).toBe(12)
    expect(capturedZone!.heightInPx).toBeGreaterThanOrEqual(240)
    expect(capturedZone!.domNode.classList.contains('ai-diff-zone')).toBe(true)

    const card = capturedZone!.domNode.querySelector('.ai-diff-card')
    const content = capturedZone!.domNode.querySelector('.ai-diff-new')
    expect(card).not.toBeNull()
    expect(content?.textContent).toBe(longText)
    expect(content?.classList.contains('ai-diff-scroll')).toBe(true)

    const buttons = capturedZone!.domNode.querySelectorAll<HTMLButtonElement>('button')
    expect(Array.from(buttons).map((button) => button.textContent)).toEqual(['接受', '拒绝'])
    buttons[0].click()
    buttons[1].click()
    expect(onAccept).toHaveBeenCalledOnce()
    expect(onReject).toHaveBeenCalledOnce()

    view.remove()
    expect(removeZone).toHaveBeenCalledWith('zone_1')
  })

  it('uses a full-width zone at the top for whole-file previews', () => {
    let capturedAfterLine = -1
    const editor = {
      changeViewZones(
        callback: (accessor: {
          addZone: (zone: { afterLineNumber: number }) => string
          removeZone: (id: string) => void
        }) => void,
      ) {
        callback({
          addZone: (zone) => {
            capturedAfterLine = zone.afterLineNumber
            return 'zone_top'
          },
          removeZone: () => undefined,
        })
      },
    }

    addInlineDiffViewZone(editor, {
      afterLineNumber: 0,
      newText: '完整文件预览',
      title: '建议修改',
      acceptLabel: '接受',
      rejectLabel: '拒绝',
      onAccept: () => undefined,
      onReject: () => undefined,
    })

    expect(capturedAfterLine).toBe(0)
  })
})
