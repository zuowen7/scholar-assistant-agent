import { beforeEach, describe, expect, it } from 'vitest'

import {
  activeEdit,
  clearActiveEdit,
  inlineDiffVisible,
  setActiveEdit,
  setInlineDiffVisible,
  shouldShowApprovalFallback,
} from '../composables/useEditorState'

const pendingEdit = {
  editId: 'edit_1',
  eventId: 'edit_1',
  sessionId: 'session_1',
  operation: 'str_replace' as const,
  filePath: 'draft/main.md',
  oldText: 'old',
  newText: 'new',
}

describe('inline diff approval fallback', () => {
  beforeEach(() => {
    clearActiveEdit()
  })

  it('keeps the ordinary approval card visible until Monaco confirms the diff widget', () => {
    setActiveEdit(pendingEdit)

    expect(activeEdit.value).toEqual(pendingEdit)
    expect(inlineDiffVisible.value).toBe(false)
    expect(shouldShowApprovalFallback(true, inlineDiffVisible.value)).toBe(true)

    setInlineDiffVisible(true)
    expect(shouldShowApprovalFallback(true, inlineDiffVisible.value)).toBe(false)
  })

  it('restores the approval fallback when the diff widget is cleared or cannot render', () => {
    setActiveEdit(pendingEdit)
    setInlineDiffVisible(true)
    clearActiveEdit()

    expect(activeEdit.value).toBeNull()
    expect(inlineDiffVisible.value).toBe(false)
    expect(shouldShowApprovalFallback(true, inlineDiffVisible.value)).toBe(true)
  })
})
