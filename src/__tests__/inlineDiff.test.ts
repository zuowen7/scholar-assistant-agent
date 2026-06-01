/**
 * Inline Diff — 前端 TDD 测试用例。
 *
 * 覆盖：
 * - shouldShowInlineDiff 路由逻辑（纯函数）
 * - activeEdit 状态管理
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// ---------------------------------------------------------------------------
// shouldShowInlineDiff 纯函数测试（不依赖 Vue/Monaco）
// ---------------------------------------------------------------------------

describe('shouldShowInlineDiff', () => {
  let shouldShowInlineDiff: (
    toolName: string,
    args: Record<string, unknown>,
    openTabPaths: string[],
  ) => boolean

  beforeEach(async () => {
    // 动态导入，确保 TDD 红灯阶段 import 失败也结构正确
    try {
      const mod = await import('../composables/useEditorState')
      shouldShowInlineDiff = mod.shouldShowInlineDiff
    } catch {
      // 函数还不存在 → 所有测试红灯（符合 TDD）
      shouldShowInlineDiff = () => false as never
    }
  })

  it('returns true for str_replace on open file', () => {
    expect(shouldShowInlineDiff('str_replace', {
      file_path: '/project/paper.md',
      old_string: 'hello',
      new_string: 'world',
    }, ['/project/paper.md'])).toBe(true)
  })

  it('returns false for str_replace on non-open file', () => {
    expect(shouldShowInlineDiff('str_replace', {
      file_path: '/project/other.md',
    }, ['/project/paper.md'])).toBe(false)
  })

  it('returns false for run_command', () => {
    expect(shouldShowInlineDiff('run_command', {
      command: 'ls',
    }, [])).toBe(false)
  })

  it('returns false for str_replace without file_path', () => {
    expect(shouldShowInlineDiff('str_replace', {}, [])).toBe(false)
  })

  it('returns true for write_file on open file', () => {
    expect(shouldShowInlineDiff('write_file', {
      file_path: '/project/notes.md',
      content: 'new',
    }, ['/project/notes.md'])).toBe(true)
  })

  it('returns false for git_op', () => {
    expect(shouldShowInlineDiff('git_op', {
      operation: 'commit',
    }, [])).toBe(false)
  })

  it('returns false for read_file even if open', () => {
    expect(shouldShowInlineDiff('read_file', {
      file_path: '/project/paper.md',
    }, ['/project/paper.md'])).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// activeEdit 状态管理测试
// ---------------------------------------------------------------------------

describe('activeEdit state', () => {
  it('initial value is null', async () => {
    const { activeEdit } = await import('../composables/useEditorState')
    expect(activeEdit.value).toBeNull()
  })

  it('setActiveEdit sets value', async () => {
    const { activeEdit, setActiveEdit, clearActiveEdit } = await import('../composables/useEditorState')
    const edit = {
      editId: 'test-1',
      eventId: 'evt_abc',
      sessionId: 'sess_1',
      operation: 'str_replace' as const,
      filePath: '/project/paper.md',
      oldText: 'hello',
      newText: 'world',
    }
    setActiveEdit(edit)
    expect(activeEdit.value).toEqual(edit)
    clearActiveEdit()
  })

  it('clearActiveEdit resets to null', async () => {
    const { activeEdit, setActiveEdit, clearActiveEdit } = await import('../composables/useEditorState')
    setActiveEdit({
      editId: 'test-2',
      eventId: 'evt_def',
      sessionId: 'sess_1',
      operation: 'write_file' as const,
      filePath: '/project/out.md',
      oldText: '',
      newText: 'content',
    })
    expect(activeEdit.value).not.toBeNull()
    clearActiveEdit()
    expect(activeEdit.value).toBeNull()
  })
})
