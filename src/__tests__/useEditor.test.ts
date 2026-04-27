/**
 * Tests for the useEditor composable.
 *
 * useEditor uses module-level singletons, so between tests we must reset the
 * reactive state manually through the composable's own API (closeTab, etc.).
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'

// ---------------------------------------------------------------------------
// Mock external modules before importing the composable
// ---------------------------------------------------------------------------

// Mock monaco-editor — the composable imports `monaco.Range` at module level
vi.mock('monaco-editor', () => ({
  Range: class Range {
    constructor(
      public startLineNumber: number,
      public startColumn: number,
      public endLineNumber: number,
      public endColumn: number,
    ) {}
  },
  editor: {},
}))

// Mock the API_BASE so import.meta.env is not needed at runtime
vi.mock('../utils/api', () => ({
  API_BASE: 'http://127.0.0.1:18088',
}))

// Mock @tauri-apps/plugin-fs so saveFile does not crash
vi.mock('@tauri-apps/plugin-fs', () => ({
  writeTextFile: vi.fn().mockResolvedValue(undefined),
}))

// ---------------------------------------------------------------------------
// Import the composable under test
// ---------------------------------------------------------------------------
import { useEditor } from '../composables/useEditor'
import type { EditorSelection } from '../types'

describe('useEditor composable', () => {
  // Obtain a fresh handle — because useEditor returns module-level singletons,
  // we reset via its own methods before each test.
  let editor: ReturnType<typeof useEditor>

  beforeEach(() => {
    editor = useEditor()

    // Close all existing tabs to reset singleton state
    const tabIds = editor.tabs.value.map(t => t.id)
    for (const id of tabIds) {
      editor.closeTab(id)
    }

    // Reset selection
    editor.updateSelection({
      startLine: 0,
      endLine: 0,
      startCol: 0,
      endCol: 0,
      text: '',
    })
  })

  // ── Initial state ──────────────────────────────────────────────────────
  describe('initial state', () => {
    it('has no tabs', () => {
      expect(editor.tabs.value).toEqual([])
    })

    it('has activeTabId as null', () => {
      expect(editor.activeTabId.value).toBeNull()
    })

    it('has empty content', () => {
      expect(editor.content.value).toBe('')
    })

    it('has activeTab as null', () => {
      expect(editor.activeTab.value).toBeNull()
    })

    it('has activeFile as null', () => {
      expect(editor.activeFile.value).toBeNull()
    })

    it('has contentVersion at 0', () => {
      expect(editor.contentVersion.value).toBe(0)
    })

    it('has empty selection text', () => {
      expect(editor.selection.value.text).toBe('')
    })
  })

  // ── openFile ───────────────────────────────────────────────────────────
  describe('openFile', () => {
    it('creates a new tab with the file path as id', () => {
      editor.openFile('/docs/readme.md', '# Readme')

      expect(editor.tabs.value).toHaveLength(1)
      const tab = editor.tabs.value[0]
      expect(tab.id).toBe('/docs/readme.md')
      expect(tab.path).toBe('/docs/readme.md')
      expect(tab.name).toBe('readme.md')
      expect(tab.content).toBe('# Readme')
      expect(tab.isModified).toBe(false)
    })

    it('sets the active tab', () => {
      editor.openFile('/a.md', 'aaa')

      expect(editor.activeTabId.value).toBe('/a.md')
      expect(editor.activeTab.value?.name).toBe('a.md')
    })

    it('switches to existing tab if file is already open', () => {
      editor.openFile('/x.md', 'original')
      editor.openFile('/y.md', 'other')
      editor.openFile('/x.md', 'updated')

      expect(editor.tabs.value).toHaveLength(2)
      // Should switch back to x.md
      expect(editor.activeTabId.value).toBe('/x.md')
      // Content should be updated because text was provided
      expect(editor.activeTab.value?.content).toBe('updated')
    })

    it('does not update content of existing tab if text is empty', () => {
      editor.openFile('/x.md', 'original')
      editor.openFile('/y.md', '')
      editor.openFile('/x.md', '') // no text → no update

      expect(editor.activeTab.value?.content).toBe('original')
    })

    it('extracts filename from path with forward slashes', () => {
      editor.openFile('/home/user/documents/paper.md')
      expect(editor.activeTab.value?.name).toBe('paper.md')
    })

    it('extracts filename from path with backslashes', () => {
      editor.openFile('C:\\Users\\docs\\notes.txt')
      expect(editor.activeTab.value?.name).toBe('notes.txt')
    })

    it('defaults name to Untitled when path has no segments', () => {
      editor.openFile('')
      expect(editor.activeTab.value?.name).toBe('Untitled')
    })
  })

  // ── openNewUntitled ────────────────────────────────────────────────────
  describe('openNewUntitled', () => {
    it('creates a tab with null path', () => {
      editor.openNewUntitled()

      expect(editor.tabs.value).toHaveLength(1)
      const tab = editor.tabs.value[0]
      expect(tab.path).toBeNull()
      expect(tab.name).toBe('Untitled')
      expect(tab.content).toBe('')
    })

    it('generates an id starting with untitled-', () => {
      editor.openNewUntitled()

      const tab = editor.tabs.value[0]
      expect(tab.id).toMatch(/^untitled-\d+$/)
    })

    it('two untitled tabs have different ids', () => {
      let counter = 1000
      const spy = vi.spyOn(Date, 'now').mockImplementation(() => counter++)

      editor.openNewUntitled()
      editor.openNewUntitled()

      const [first, second] = editor.tabs.value
      expect(first.id).not.toBe(second.id)

      spy.mockRestore()
    })

    it('sets the new tab as active', () => {
      editor.openNewUntitled()
      expect(editor.activeTab.value?.name).toBe('Untitled')
    })
  })

  // ── closeTab ───────────────────────────────────────────────────────────
  describe('closeTab', () => {
    it('removes the specified tab', () => {
      editor.openFile('/a.md', 'a')
      editor.openFile('/b.md', 'b')

      editor.closeTab('/a.md')

      expect(editor.tabs.value).toHaveLength(1)
      expect(editor.tabs.value[0].id).toBe('/b.md')
    })

    it('switches to next tab when closing the active tab', () => {
      editor.openFile('/a.md', 'a')
      editor.openFile('/b.md', 'b')
      editor.openFile('/c.md', 'c')
      // active is /c.md

      editor.closeTab('/c.md')

      // Should activate /b.md (the previous one, since c was the last)
      expect(editor.activeTabId.value).toBe('/b.md')
    })

    it('activates previous tab when closing the last tab', () => {
      editor.openFile('/first.md', '1')
      editor.openFile('/last.md', '2')

      editor.closeTab('/last.md')

      expect(editor.activeTabId.value).toBe('/first.md')
    })

    it('sets activeTabId to null when closing the only tab', () => {
      editor.openFile('/only.md', 'solo')
      editor.closeTab('/only.md')

      expect(editor.tabs.value).toHaveLength(0)
      expect(editor.activeTabId.value).toBeNull()
    })

    it('does nothing for a non-existent tab id', () => {
      editor.openFile('/exists.md', 'content')
      editor.closeTab('does-not-exist')

      expect(editor.tabs.value).toHaveLength(1)
    })
  })

  // ── setContent ─────────────────────────────────────────────────────────
  describe('setContent', () => {
    it('updates active tab content', () => {
      editor.openFile('/doc.md', 'old')
      editor.setContent('new content')

      expect(editor.content.value).toBe('new content')
      expect(editor.activeTab.value?.content).toBe('new content')
    })

    it('increments contentVersion', () => {
      const before = editor.contentVersion.value
      editor.openFile('/doc.md', '')
      editor.setContent('changed')

      expect(editor.contentVersion.value).toBe(before + 1)
    })

    it('does nothing when no tab is active', () => {
      // No tab open
      editor.setContent('something')
      expect(editor.content.value).toBe('')
    })
  })

  // ── updateSelection ────────────────────────────────────────────────────
  describe('updateSelection', () => {
    it('updates the selection ref', () => {
      const sel: EditorSelection = {
        startLine: 1,
        endLine: 3,
        startCol: 0,
        endCol: 15,
        text: 'selected text',
      }

      editor.updateSelection(sel)

      expect(editor.selection.value).toEqual(sel)
      expect(editor.selection.value.text).toBe('selected text')
    })

    it('can be updated multiple times', () => {
      editor.updateSelection({ startLine: 1, endLine: 1, startCol: 0, endCol: 5, text: 'hello' })
      editor.updateSelection({ startLine: 2, endLine: 4, startCol: 0, endCol: 10, text: 'world' })

      expect(editor.selection.value.text).toBe('world')
      expect(editor.selection.value.startLine).toBe(2)
    })
  })

  // ── setActiveTab / switchTab ───────────────────────────────────────────
  describe('setActiveTab', () => {
    it('switches to the specified tab', () => {
      editor.openFile('/a.md', 'aaa')
      editor.openFile('/b.md', 'bbb')

      expect(editor.activeTabId.value).toBe('/b.md')

      editor.setActiveTab('/a.md')

      expect(editor.activeTabId.value).toBe('/a.md')
      expect(editor.content.value).toBe('aaa')
    })

    it('does nothing if the id does not exist', () => {
      editor.openFile('/a.md', 'aaa')
      editor.setActiveTab('nonexistent')

      expect(editor.activeTabId.value).toBe('/a.md')
    })
  })

  // ── markClean / markDirty ──────────────────────────────────────────────
  describe('markClean and markDirty', () => {
    it('markClean sets isModified to false', () => {
      editor.openFile('/a.md', 'content')
      editor.markDirty()
      expect(editor.activeTab.value?.isModified).toBe(true)

      editor.markClean()
      expect(editor.activeTab.value?.isModified).toBe(false)
    })

    it('markDirty sets isModified to true and increments contentVersion', () => {
      editor.openFile('/a.md', '')
      const before = editor.contentVersion.value

      editor.markDirty()

      expect(editor.activeTab.value?.isModified).toBe(true)
      expect(editor.contentVersion.value).toBe(before + 1)
    })
  })

  // ── Mixed workflow ─────────────────────────────────────────────────────
  describe('mixed workflow', () => {
    it('open several files, switch, close, and verify state', () => {
      editor.openFile('/intro.md', '# Intro')
      editor.openFile('/methods.md', '## Methods')
      editor.openNewUntitled()

      expect(editor.tabs.value).toHaveLength(3)

      // Switch to methods
      editor.setActiveTab('/methods.md')
      expect(editor.content.value).toBe('## Methods')

      // Close methods
      editor.closeTab('/methods.md')
      expect(editor.tabs.value).toHaveLength(2)
      // Active should be the last tab (untitled) since methods was in the middle
      // The closeTab logic: idx=1, tabs left = 2, idx < length → activate tabs[1]
      expect(editor.activeTab.value?.name).toBe('Untitled')

      // Switch to intro
      editor.setActiveTab('/intro.md')
      editor.setContent('# Introduction (updated)')
      expect(editor.content.value).toBe('# Introduction (updated)')
    })
  })
})
