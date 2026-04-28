/**
 * Tests for the editor state composables (split architecture).
 *
 * useEditorState:   module-level singleton state (tabs, selection, etc.)
 * useEditorTabs:    tab/file operations (openFile, closeTab, etc.)
 * useEditor:        AI edit, inline edit, ghost text
 *
 * The test imports state directly and actions from the appropriate modules.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'

// ---------------------------------------------------------------------------
// Mock external modules
// ---------------------------------------------------------------------------

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

vi.mock('../utils/api', () => ({
  API_BASE: 'http://127.0.0.1:18088',
}))

vi.mock('@tauri-apps/plugin-fs', () => ({
  writeTextFile: vi.fn().mockResolvedValue(undefined),
}))

// ---------------------------------------------------------------------------
// Import the real module-level singletons
// ---------------------------------------------------------------------------

import {
  tabs, activeTabId, activeTab, content, activeFile,
  contentVersion, selection, monacoEditor,
  aiResult, previousContent,
} from '../composables/useEditorState'

import {
  openFile, openNewUntitled, closeTab, setActiveTab,
  setContent, updateSelection, markClean, markDirty, saveFile,
} from '../composables/useEditorTabs'

describe('editor state composables (split)', () => {
  beforeEach(() => {
    // Close all existing tabs to reset singleton state
    const ids = tabs.value.map((t: { id: string }) => t.id)
    for (const id of ids) { closeTab(id) }
    selection.value = { startLine: 0, endLine: 0, startCol: 0, endCol: 0, text: '' }
  })

  // ── Initial state ──────────────────────────────────────────────────────
  describe('initial state', () => {
    it('has no tabs', () => { expect(tabs.value).toEqual([]) })
    it('has activeTabId as null', () => { expect(activeTabId.value).toBeNull() })
    it('has empty content', () => { expect(content.value).toBe('') })
    it('has activeTab as null', () => { expect(activeTab.value).toBeNull() })
    it('has activeFile as null', () => { expect(activeFile.value).toBeNull() })
    it('has contentVersion at 0', () => { expect(contentVersion.value).toBe(0) })
    it('has empty selection text', () => { expect(selection.value.text).toBe('') })
  })

  // ── openFile ───────────────────────────────────────────────────────────
  describe('openFile', () => {
    it('creates a new tab with the file path as id', () => {
      openFile('/docs/readme.md', '# Readme')
      expect(tabs.value).toHaveLength(1)
      expect(tabs.value[0].id).toBe('/docs/readme.md')
      expect(tabs.value[0].path).toBe('/docs/readme.md')
      expect(tabs.value[0].name).toBe('readme.md')
      expect(tabs.value[0].content).toBe('# Readme')
      expect(tabs.value[0].isModified).toBe(false)
    })

    it('sets the active tab', () => {
      openFile('/a.md', 'aaa')
      expect(activeTabId.value).toBe('/a.md')
      expect(activeTab.value?.name).toBe('a.md')
    })

    it('switches to existing tab if file is already open', () => {
      openFile('/x.md', 'original')
      openFile('/y.md', 'other')
      openFile('/x.md', 'updated')
      expect(tabs.value).toHaveLength(2)
      expect(activeTabId.value).toBe('/x.md')
      expect(activeTab.value?.content).toBe('updated')
    })

    it('does not update content of existing tab if text is empty', () => {
      openFile('/x.md', 'original')
      openFile('/y.md', '')
      openFile('/x.md', '')
      expect(activeTab.value?.content).toBe('original')
    })

    it('extracts filename from path with forward slashes', () => {
      openFile('/home/user/documents/paper.md')
      expect(activeTab.value?.name).toBe('paper.md')
    })

    it('extracts filename from path with backslashes', () => {
      openFile('C:\\Users\\docs\\notes.txt')
      expect(activeTab.value?.name).toBe('notes.txt')
    })

    it('defaults name to Untitled when path has no segments', () => {
      openFile('')
      expect(activeTab.value?.name).toBe('Untitled')
    })
  })

  // ── openNewUntitled ────────────────────────────────────────────────────
  describe('openNewUntitled', () => {
    it('creates a tab with null path', () => {
      openNewUntitled()
      expect(tabs.value).toHaveLength(1)
      expect(tabs.value[0].path).toBeNull()
      expect(tabs.value[0].name).toBe('Untitled')
      expect(tabs.value[0].content).toBe('')
    })

    it('generates an id starting with untitled-', () => {
      openNewUntitled()
      expect(tabs.value[0].id).toMatch(/^untitled-\d+$/)
    })

    it('two untitled tabs have different ids', () => {
      let counter = 1000
      const spy = vi.spyOn(Date, 'now').mockImplementation(() => counter++)
      openNewUntitled()
      openNewUntitled()
      const [first, second] = tabs.value
      expect(first.id).not.toBe(second.id)
      spy.mockRestore()
    })

    it('sets the new tab as active', () => {
      openNewUntitled()
      expect(activeTab.value?.name).toBe('Untitled')
    })
  })

  // ── closeTab ───────────────────────────────────────────────────────────
  describe('closeTab', () => {
    it('removes the specified tab', () => {
      openFile('/a.md', 'a')
      openFile('/b.md', 'b')
      closeTab('/a.md')
      expect(tabs.value).toHaveLength(1)
      expect(tabs.value[0].id).toBe('/b.md')
    })

    it('switches to next tab when closing the active tab', () => {
      openFile('/a.md', 'a')
      openFile('/b.md', 'b')
      openFile('/c.md', 'c')
      closeTab('/c.md')
      expect(activeTabId.value).toBe('/b.md')
    })

    it('activates previous tab when closing the last tab', () => {
      openFile('/first.md', '1')
      openFile('/last.md', '2')
      closeTab('/last.md')
      expect(activeTabId.value).toBe('/first.md')
    })

    it('sets activeTabId to null when closing the only tab', () => {
      openFile('/only.md', 'solo')
      closeTab('/only.md')
      expect(tabs.value).toHaveLength(0)
      expect(activeTabId.value).toBeNull()
    })

    it('does nothing for a non-existent tab id', () => {
      openFile('/exists.md', 'content')
      closeTab('does-not-exist')
      expect(tabs.value).toHaveLength(1)
    })
  })

  // ── setContent ─────────────────────────────────────────────────────────
  describe('setContent', () => {
    it('updates active tab content', () => {
      openFile('/doc.md', 'old')
      setContent('new content')
      expect(content.value).toBe('new content')
      expect(activeTab.value?.content).toBe('new content')
    })

    it('increments contentVersion', () => {
      const before = contentVersion.value
      openFile('/doc.md', '')
      setContent('changed')
      expect(contentVersion.value).toBe(before + 1)
    })

    it('does nothing when no tab is active', () => {
      setContent('something')
      expect(content.value).toBe('')
    })
  })

  // ── updateSelection ───────────────────────────────────────────────────
  describe('updateSelection', () => {
    it('updates the selection ref', () => {
      const sel = { startLine: 1, endLine: 3, startCol: 0, endCol: 15, text: 'selected text' }
      updateSelection(sel)
      expect(selection.value).toEqual(sel)
      expect(selection.value.text).toBe('selected text')
    })

    it('can be updated multiple times', () => {
      updateSelection({ startLine: 1, endLine: 1, startCol: 0, endCol: 5, text: 'hello' })
      updateSelection({ startLine: 2, endLine: 4, startCol: 0, endCol: 10, text: 'world' })
      expect(selection.value.text).toBe('world')
      expect(selection.value.startLine).toBe(2)
    })
  })

  // ── setActiveTab ──────────────────────────────────────────────────────
  describe('setActiveTab', () => {
    it('switches to the specified tab', () => {
      openFile('/a.md', 'aaa')
      openFile('/b.md', 'bbb')
      expect(activeTabId.value).toBe('/b.md')
      setActiveTab('/a.md')
      expect(activeTabId.value).toBe('/a.md')
      expect(content.value).toBe('aaa')
    })

    it('does nothing if the id does not exist', () => {
      openFile('/a.md', 'aaa')
      setActiveTab('nonexistent')
      expect(activeTabId.value).toBe('/a.md')
    })
  })

  // ── markClean / markDirty ──────────────────────────────────────────────
  describe('markClean and markDirty', () => {
    it('markClean sets isModified to false', () => {
      openFile('/a.md', 'content')
      markDirty()
      expect(activeTab.value?.isModified).toBe(true)
      markClean()
      expect(activeTab.value?.isModified).toBe(false)
    })

    it('markDirty sets isModified to true and increments contentVersion', () => {
      openFile('/a.md', '')
      const before = contentVersion.value
      markDirty()
      expect(activeTab.value?.isModified).toBe(true)
      expect(contentVersion.value).toBe(before + 1)
    })
  })

  // ── Mixed workflow ─────────────────────────────────────────────────────
  describe('mixed workflow', () => {
    it('open several files, switch, close, and verify state', () => {
      openFile('/intro.md', '# Intro')
      openFile('/methods.md', '## Methods')
      openNewUntitled()
      expect(tabs.value).toHaveLength(3)
      setActiveTab('/methods.md')
      expect(content.value).toBe('## Methods')
      closeTab('/methods.md')
      expect(tabs.value).toHaveLength(2)
      expect(activeTab.value?.name).toBe('Untitled')
      setActiveTab('/intro.md')
      setContent('# Introduction (updated)')
      expect(content.value).toBe('# Introduction (updated)')
    })
  })
})