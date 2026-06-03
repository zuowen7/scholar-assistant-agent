<template>
  <div class="editor-layout">
    <!-- 左侧文件树 -->
    <div
      class="layout-sidebar"
      :class="{ collapsed: sidebarCollapsed }"
      :style="{ width: (sidebarCollapsed ? collapsedSidebarWidth : sidebarWidth) + 'px' }"
    >
      <FileTree v-if="!sidebarCollapsed" @collapse="sidebarCollapsed = true" />
      <button v-else class="sidebar-rail-button" @click="sidebarCollapsed = false">
        Explorer
      </button>
    </div>
    <div
      v-if="!sidebarCollapsed"
      class="resize-handle sidebar-resize"
      @mousedown="startResize($event, 'sidebar')"
    ></div>

    <!-- 中间编辑器 -->
    <div class="layout-editor">
      <MindMapView
        v-if="workspaceMode === 'mindmap'"
        @enter-editor="enterEditorFromMindMap"
      />

      <template v-else>
        <EditorTabs v-if="activeTab" />

        <!-- Welcome screen (extracted to EditorWelcome.vue) -->
        <EditorWelcome
          v-if="!activeTab"
          @new-project="showProjectStart = true"
          @open-template="showTemplatePicker = true"
          @open-folder="openWorkspaceFolder"
          @new-document="openNewUntitled"
        />

        <!-- Active editor -->
        <template v-else>
          <!-- Slim toolbar (extracted to EditorToolbar.vue) -->
          <EditorToolbar
            ref="toolbarRef"
            :active-right-tab="rightPanelTab"
            :templates="exportTemplates"
            :selected-template="selectedTemplate"
            :export-loading="exportLoading"
            :message="exportMessage"
            @new-paper="showTemplatePicker = true"
            @save="handleSaveFile"
            @open-mindmap="openMindMapFromEditor"
            @toggle-right="toggleRightPanel"
            @select-template="selectedTemplate = $event"
            @image-selected="handleImageSelected"
            @vision-selected="handleVisionSelected"
            @insert-table="insertTable"
            @insert-inline-formula="insertInlineFormula"
            @insert-block-formula="insertBlockFormula"
            @run-compliance="runComplianceCheck"
            @process-citations="handleProcessCitations"
            @zotero-insert="handleZoteroInsert"
            @export-word="handleExportWord"
            @export-latex="handleExportLatex"
            @export-pdf="handleExportPdf"
            @voice-start="handleVoiceStart"
            @voice-update="handleVoiceUpdate"
            @voice-stop="handleVoiceStop"
          />

          <MonacoEditor
            :theme="isDark ? 'vs-dark' : 'vs'"
            @contentChange="onContentChange"
            @selectionChange="onSelectionChange"
          />
        </template>
      </template>
    </div>

    <!-- 右侧统一 Tab 面板 -->
    <div v-if="workspaceMode === 'editor' && activeTab && rightPanelTab" class="layout-panel-wrapper">
      <div class="resize-handle panel-resize" @mousedown="startResize($event, 'panel')"></div>
      <div class="layout-panel" :style="{ width: panelWidth + 'px' }">
        <EditorRightTabBar v-model="rightPanelTab" />
        <!-- Tab content -->
        <MarkdownPreview
          v-if="rightPanelTab === 'preview'"
          :content="content"
          :version="contentVersion"
          class="rp-content"
        />
        <AiPanel
          ref="aiPanelRef"
          v-if="rightPanelTab === 'ai'"
          :editor-context="selection.text || content"
          :active-file="activeFile"
          :can-undo="!!previousContent"
          :workspace-files="workspaceFiles"
          class="rp-content"
          @insert="handleInsert"
          @undo="handleUndo"
          @close="rightPanelTab = null"
        />
        <CompanionPanel v-if="rightPanelTab === 'argument'" :content="content" class="rp-content" />
      </div>
    </div>

    <!-- Modals -->
    <EditorCompliance
      :visible="showCompliance"
      :loading="complianceLoading"
      :error="complianceError"
      :report="complianceReport"
      @close="showCompliance = false"
      @retry="runComplianceCheck"
    />

    <TemplatePicker
      :visible="showTemplatePicker"
      :isDark="isDark"
      @close="showTemplatePicker = false"
      @create="handleScaffoldCreate"
    />

    <EditorNewProject
      :visible="showProjectStart"
      @close="showProjectStart = false"
      @enter-editor="startProjectInEditor"
      @enter-mindmap="startProjectWithMindMap"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

// -- Layout sub-components ------------------------------------------------
import EditorWelcome from './EditorWelcome.vue'
import EditorToolbar from './EditorToolbar.vue'
import EditorNewProject from './EditorNewProject.vue'
import EditorCompliance from './EditorCompliance.vue'
import EditorTabs from './EditorTabs.vue'
import EditorRightTabBar from './EditorRightTabBar.vue'
import MonacoEditor from './MonacoEditor.vue'
import MarkdownPreview from './MarkdownPreview.vue'
import FileTree from './FileTree.vue'
import AiPanel from './AiPanel.vue'
import ArgumentMapMini from './argument/ArgumentMapMini.vue'
import CompanionPanel from './argument/CompanionPanel.vue'
import ComplianceModal from './ComplianceModal.vue'
import TemplatePicker from './TemplatePicker.vue'
import MindMapView from './MindMapView.vue'

// -- State composables ---------------------------------------------------
import { useEditorState, getRange } from '../composables/useEditorState'
import { useEditor } from '../composables/useEditor'
import { useEditorVision } from '../composables/useEditorVision'
import { useEditorCitation } from '../composables/useEditorCitation'
import { useEditorIO } from '../composables/useEditorIO'
import { useMindMap, markdownToMindMapNodes } from '../composables/useMindMap'
import { useArgumentCompanion } from '../composables/useArgumentCompanion'
import { API_BASE } from '../utils/api'

const props = defineProps<{ isDark: boolean }>()

// -- Shared singleton state (single source of truth) ---------------------
const { activeTab, content, contentVersion, selection, previousContent, tabs, aiResult, insertTextAtCursor, activeFile } = useEditorState()

// -- Tab / file operations ------------------------------------------------
const {
  openNewUntitled, setContent, markDirty,
  saveFile,
} = useEditor()

// -- AI edit actions (from useEditor, called once) -----------------------
const { aiEdit, applyAiResult, undoEdit } = useEditor()

// -- Feature composables ---------------------------------------------------
const { analyzeVision, uploadImage, insertImageFile } = useEditorVision()
const { processCitations, previewCitations, getZoteroStatus, searchZotero } = useEditorCitation()
const { exportToWord, exportLatex, exportPdf, loadExportTemplates } = useEditorIO()
const { resetMindMap, loadSavedMindMap, saveMindMap, addChild, updateNodeText, updateNodeBody, skipNextBackendLoad } = useMindMap()

// -- Workspace mode -------------------------------------------------------
const workspaceMode = ref<'editor' | 'mindmap'>('editor')
let _contentBeforeMindMap = ''
const sidebarCollapsed = ref(false)
const collapsedSidebarWidth = 44

// -- Right panel ----------------------------------------------------------
type RightTab = 'preview' | 'ai' | 'argument'
const rightPanelTab = ref<RightTab | null>(null)
const aiPanelRef = ref<InstanceType<typeof AiPanel> | null>(null)
const toggleRightPanel = (tab: RightTab) => { rightPanelTab.value = rightPanelTab.value === tab ? null : tab }

// -- Export state ---------------------------------------------------------
const exportTemplates = ref<{ id: string; name: string }[]>([])
const selectedTemplate = ref('')
const exportLoading = ref(false)
const exportMessage = ref('')
const toolbarRef = ref<InstanceType<typeof EditorToolbar> | null>(null)
let exportToastTimer: ReturnType<typeof setTimeout> | null = null
const tectonicAvailable = ref(false)

// -- Compliance ------------------------------------------------------------
const showCompliance = ref(false)
const complianceLoading = ref(false)
const complianceError = ref('')
const complianceReport = ref<Record<string, unknown> | null>(null)

// -- Template picker / project start -------------------------------------
const showTemplatePicker = ref(false)
const showProjectStart = ref(false)

// M12 fix: only map stable identity fields (name/path) so this computed does NOT
// invalidate on every keystroke when tab content changes.  AiPanel needs `content`
// only when the user actually selects a file via @-mention; it accesses it through
// the `content` field which we populate lazily via a getter below.
const workspaceFiles = computed(() =>
  tabs.value.map(t => {
    const name = t.name || t.path?.split(/[\\/]/).pop() || 'untitled'
    // Expose content as a lazy getter so Vue's reactivity system does not track
    // it as a dependency of this computed — content is large and changes on every
    // edit, but only matters when a user explicitly @-mentions the file.
    const tab = t
    return Object.defineProperty({ name }, 'content', {
      get() { return tab.content },
      enumerable: true,
      configurable: true,
    }) as { name: string; content?: string }
  })
)

// -- Event handlers ------------------------------------------------------

async function openWorkspaceFolder() {
  try {
    const { open } = await import('@tauri-apps/plugin-dialog')
    const selected = await open({ directory: true, multiple: false })
    if (selected) window.dispatchEvent(new CustomEvent('open-workspace-folder', { detail: { path: selected } }))
  } catch { /* cancelled */ }
}

function handleScaffoldCreate(markdown: string, templateId: string) {
  openNewUntitled()
  nextTick(() => {
    if (activeTab.value) {
      activeTab.value.content = markdown
      activeTab.value.name = `${templateId}-paper.md`
    }
  })
}

function startProjectInEditor() {
  showProjectStart.value = false
  workspaceMode.value = 'editor'
  openNewUntitled()
}

function startProjectWithMindMap(topic: string) {
  showProjectStart.value = false
  sidebarCollapsed.value = true
  resetMindMap(topic.trim() || undefined)
  workspaceMode.value = 'mindmap'
}

function enterEditorFromMindMap(outline: string) {
  saveMindMap()
  workspaceMode.value = 'editor'
  if (!activeTab.value) openNewUntitled()
  nextTick(() => {
    if (!activeTab.value) return
    if (outline.trim()) {
      setContent(outline)
    } else if (_contentBeforeMindMap) {
      setContent(_contentBeforeMindMap)
    }
  })
  _contentBeforeMindMap = ''
}

function buildTreeNode(parentId: string, node: import('../composables/useMindMap').MindMapTreeNode) {
  const mm = useMindMap()
  addChild(parentId)
  const nodeId = mm.selectedNodeId.value
  updateNodeText(nodeId, node.text)
  if (node.body) updateNodeBody(nodeId, node.body)
  for (const child of node.children) {
    buildTreeNode(nodeId, child)
  }
}

function openMindMapFromEditor() {
  sidebarCollapsed.value = true
  skipNextBackendLoad()
  _contentBeforeMindMap = content.value
  const md = content.value
  if (md.trim()) {
    const tree = markdownToMindMapNodes(md)
    const mm = useMindMap()
    if (tree) {
      resetMindMap(tree.text)
      const rootId = mm.draftMindMap.value.rootId
      if (tree.body) updateNodeBody(rootId, tree.body)
      for (const child of tree.children) {
        buildTreeNode(rootId, child)
      }
      mm.selectNode(rootId)
    } else {
      // No headings found — create root node with full text as body
      resetMindMap('')
      const rootId = mm.draftMindMap.value.rootId
      updateNodeBody(rootId, md.trim())
      mm.selectNode(rootId)
    }
  } else {
    loadSavedMindMap()
  }
  workspaceMode.value = 'mindmap'
}

async function handleSaveFile() {
  const err = await saveFile()
  showExportToast(err || t('editor.saved'))
}

async function handleExportWord() {
  if (exportLoading.value) return
  exportLoading.value = true
  try {
    const title = (activeTab.value?.name || t('editor.yamDraft')).replace(/\.md$/i, '')
    const err = await exportToWord(content.value, title)
    showExportToast(err || t('editor.wordExportStarted'))
  } catch (e) { showExportToast(t('editor.wordExportFailed', { msg: String(e) }))
  } finally { exportLoading.value = false }
}

async function handleExportLatex() {
  if (!selectedTemplate.value || exportLoading.value) return
  if (!content.value.trim()) { showExportToast(t('editor.pleaseInputContent')); return }
  exportLoading.value = true
  try {
    const { tex, error } = await exportLatex(content.value, selectedTemplate.value)
    if (error) { showExportToast(error); return }
    if (tex) { await navigator.clipboard.writeText(tex); showExportToast(t('editor.latexCopied')) }
    else showExportToast(t('editor.conversionEmpty'))
  } catch (e) { showExportToast(t('editor.exportFailed', { msg: String(e) }))
  } finally { exportLoading.value = false }
}

async function handleExportPdf() {
  if (!selectedTemplate.value || exportLoading.value) return
  if (!content.value.trim()) { showExportToast(t('editor.pleaseInputContent')); return }
  if (!tectonicAvailable.value) {
    const { tectonic_available } = await loadExportTemplates()
    tectonicAvailable.value = tectonic_available
    if (!tectonic_available) { showExportToast(t('editor.installTectonic')); return }
  }
  exportLoading.value = true
  try {
    const title = (activeTab.value?.name || 'paper').replace(/\.md$/i, '')
    const err = await exportPdf(content.value, selectedTemplate.value, title)
    if (err === 'Cancelled') { showExportToast(t('editor.cancelled')); return }
    showExportToast(err || t('editor.pdfSaved'))
  } catch (e) { showExportToast(t('editor.pdfExportFailed', { msg: String(e) }))
  } finally { exportLoading.value = false }
}

async function handleProcessCitations() {
  if (!content.value.trim()) { showExportToast(t('editor.pleaseInputContent')); return }
  try {
    const preview = await previewCitations(content.value)
    const data = await processCitations(content.value, [], 'ieee')
    if (!data?.text) { showExportToast(t('editor.citationFailed')); return }
    if (activeTab.value) { setContent(`${data.text}${data.bibliography || ''}`); markDirty() }
    showExportToast(t('editor.citationCount', { count: preview?.unique_count ?? data.citations?.length ?? 0 }))
  } catch (e) { showExportToast(t('editor.citationFailedMsg', { msg: String(e) })) }
}

async function handleZoteroInsert() {
  const query = window.prompt(t('editor.searchZotero'))
  if (!query?.trim()) return
  try {
    const status = await getZoteroStatus()
    if (status && status.connected === false) { showExportToast(t('editor.zoteroConfig')); return }
    const items = await searchZotero(query.trim(), 5)
    const item = items[0]
    if (!item?.key) { showExportToast(t('editor.zoteroNotFound')); return }
    const citation = item.markdown_citation || (item.citation_key ? `[@${item.citation_key}]` : '')
    if (citation) insertTextAtCursor(citation)
    showExportToast(t('editor.zoteroInserted', { key: item.citation_key || item.key }))
  } catch (e) { showExportToast(t('editor.zoteroFailed', { msg: String(e) })) }
}

async function handleImageSelected(file: File) {
  try {
    const data = await insertImageFile(file)
    showExportToast(data ? t('editor.imageInserted') : t('editor.imageUploadFailed'))
  } catch { showExportToast(t('editor.imageUploadFailed')) }
}

async function handleVisionSelected(file: File) {
  try {
    const data = await analyzeVision(file, 'general')
    if (!data) { showExportToast(t('editor.visionFailed')); return }
    const findings = data.key_findings?.length ? `\n${t('editor.visionFindings', { findings: data.key_findings.join('; ') })}` : ''
    const chart = data.chart_type ? `\n${t('editor.visionChartType', { type: data.chart_type })}` : ''
    const table = data.table_data?.length
      ? `\n\n${data.table_data.map((row: string[]) => `| ${row.join(' | ')} |`).join('\n')}`
      : ''
    insertTextAtCursor(`\n\n> Vision：${data.text || data.raw_description || t('editor.visionNoText')}${chart}${findings}${table}\n`)
    showExportToast(t('editor.visionInserted'))
  } catch (e) { showExportToast(t('editor.visionFailedMsg', { msg: String(e) })) }
}

async function runComplianceCheck() {
  if (!content.value.trim()) { complianceError.value = t('editor.editorEmpty'); showCompliance.value = true; return }
  complianceLoading.value = true
  complianceError.value = ''
  complianceReport.value = null
  showCompliance.value = true
  try {
    const resp = await fetch(`${API_BASE}/api/compliance`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        markdown: content.value,
        title: (activeTab.value?.name || 'Untitled').replace(/\.md$/i, ''),
        venue: '',
        required_sections: 'introduction, related_work, method, experiment, conclusion',
      }),
    })
    const data = await resp.json()
    if (data.error && (!data.report || !data.report.summary)) {
      complianceError.value = data.error || t('editor.complianceFailed')
    } else if (data.report?.summary) {
      complianceReport.value = data.report
    } else {
      complianceError.value = t('editor.llmFormatError')
    }
  } catch (e) { complianceError.value = t('editor.requestFailed', { msg: String(e) })
  } finally { complianceLoading.value = false }
}

function handleInsert(text: string) { aiResult.value = text; applyAiResult() }
function handleUndo() { undoEdit() }

const companion = useArgumentCompanion()

// Wire argument companion: setDoc on tab switch, onEditorEdit on content change
watch(activeTab, (tab) => {
  if (tab?.docId) companion.setDoc(tab.docId, tab.name)
}, { immediate: true })

function onContentChange(value: string) {
  companion.onEditorEdit(value)
}
function onSelectionChange(_sel: unknown) {}

function insertTable() {
  const sr = 3, sc = 3
  const header = `| ${Array.from({ length: sc }, (_, i) => `Column ${i + 1}`).join(' | ')} |`
  const sep = `| ${Array.from({ length: sc }, () => '---').join(' | ')} |`
  const body = Array.from({ length: sr - 1 }, () => `| ${Array.from({ length: sc }, () => '').join(' | ')} |`)
  insertTextAtCursor(`\n${[header, sep, ...body].join('\n')}\n`)
}
function insertInlineFormula() { insertTextAtCursor('$ $') }
function insertBlockFormula() { insertTextAtCursor('\n$$\n\n$$\n') }
// -- Voice input: in-place replacement, deduplicated by composable --
let voiceRange: { line: number; col: number; len: number } | null = null
let lastVoiceText = ''

function handleVoiceStart() {
  const ed = useEditor().monacoEditor.value
  if (!ed) return
  ed.focus()
  const pos = ed.getPosition()
  if (!pos) return
  voiceRange = { line: pos.lineNumber, col: pos.column, len: 0 }
  lastVoiceText = ''
}

function handleVoiceUpdate(text: string) {
  const ed = useEditor().monacoEditor.value
  if (!ed || !voiceRange) return
  const Range = getRange(ed)

  // If the cursor has moved away from the voice insertion region (e.g. the user
  // pressed Tab to accept a ghost-text completion), commit the previous voice
  // text and start a fresh anchor. Only insert the NEW portion so the composable's
  // accumulated text doesn't duplicate what's already in the editor.
  const pos = ed.getPosition()
  const cursorMoved = pos && (pos.lineNumber !== voiceRange.line ||
    pos.column < voiceRange.col ||
    pos.column > voiceRange.col + voiceRange.len + 1)

  if (cursorMoved) {
    const prefix = lastVoiceText.trimEnd()
    let newText = text.trimStart()
    if (prefix && newText.startsWith(prefix)) {
      newText = newText.slice(prefix.length).trimStart()
    }
    // Reset speech recognition's accumulated text so subsequent
    // onResult callbacks start fresh — prevents Chrome's continuous
    // mode from re-including old content in new results.
    toolbarRef.value?.resetVoiceAccumulated()
    voiceRange = { line: pos.lineNumber, col: pos.column, len: 0 }
    lastVoiceText = ''
    if (newText) {
      ed.executeEdits('voice', [{
        range: new Range(voiceRange.line, voiceRange.col, voiceRange.line, voiceRange.col + voiceRange.len),
        text: newText,
      }])
      voiceRange.len = newText.length
    }
    return
  }

  ed.executeEdits('voice', [{
    range: new Range(voiceRange.line, voiceRange.col, voiceRange.line, voiceRange.col + voiceRange.len),
    text,
  }])
  voiceRange.len = text.length
  lastVoiceText = text
}

function handleVoiceStop(text: string) {
  voiceRange = null
  lastVoiceText = ''
}

function showExportToast(msg: string) {
  if (exportToastTimer) clearTimeout(exportToastTimer)
  exportMessage.value = msg
  exportToastTimer = setTimeout(() => { exportMessage.value = '' }, 3000)
}

// -- Resize ---------------------------------------------------------------
const sidebarWidth = ref(296)
const panelWidth = ref(300)

let _resizeAbortController: AbortController | null = null

function startResize(e: MouseEvent, target: 'sidebar' | 'panel') {
  e.preventDefault()
  // 取消上一次未完成的 resize，防止快速多次点击导致监听器堆积
  if (_resizeAbortController) {
    _resizeAbortController.abort()
  }
  _resizeAbortController = new AbortController()
  const signal = _resizeAbortController.signal
  const startX = e.clientX
  const startWidth = target === 'sidebar' ? sidebarWidth.value : panelWidth.value
  function onMouseMove(e: MouseEvent) {
    if (target === 'sidebar') {
      sidebarWidth.value = Math.max(150, Math.min(400, startWidth + e.clientX - startX))
    } else {
      panelWidth.value = Math.max(260, Math.min(760, startWidth - (e.clientX - startX)))
    }
  }
  function onMouseUp() {
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onMouseUp)
    _resizeAbortController = null
  }
  document.addEventListener('mousemove', onMouseMove, { signal })
  document.addEventListener('mouseup', onMouseUp, { signal })
}

// -- Keyboard -------------------------------------------------------------
function onKeyDown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); handleSaveFile() }
}

// -- Lifecycle -------------------------------------------------------------
onMounted(() => {
  window.addEventListener('keydown', onKeyDown)
  loadExportTemplates().then(({ templates, tectonic_available }) => {
    exportTemplates.value = templates
    tectonicAvailable.value = tectonic_available
    if (templates.length && !selectedTemplate.value) selectedTemplate.value = templates[0].id
  })
  window.addEventListener('paper-scaffold', handlePaperScaffold as EventListener)

  // Voice command event listeners
  window.addEventListener('voice-set-mindmap', handleVoiceSetMindmap)
  window.addEventListener('voice-export', handleVoiceExport as EventListener)
  window.addEventListener('voice-ai-preset', handleVoiceAiPreset as EventListener)
  window.addEventListener('voice-compliance', handleVoiceCompliance)
  window.addEventListener('voice-citations', handleVoiceCitations)
  window.addEventListener('voice-open-folder', handleVoiceOpenFolder)
  window.addEventListener('voice-new-file', handleVoiceNewFile)
  window.addEventListener('voice-save', handleVoiceSave)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeyDown)
  window.removeEventListener('paper-scaffold', handlePaperScaffold as EventListener)
  window.removeEventListener('voice-set-mindmap', handleVoiceSetMindmap)
  window.removeEventListener('voice-export', handleVoiceExport as EventListener)
  window.removeEventListener('voice-ai-preset', handleVoiceAiPreset as EventListener)
  window.removeEventListener('voice-compliance', handleVoiceCompliance)
  window.removeEventListener('voice-citations', handleVoiceCitations)
  window.removeEventListener('voice-open-folder', handleVoiceOpenFolder)
  window.removeEventListener('voice-new-file', handleVoiceNewFile)
  window.removeEventListener('voice-save', handleVoiceSave)
  if (_resizeAbortController) { _resizeAbortController.abort(); _resizeAbortController = null }
})

function handlePaperScaffold(e: Event) {
  const { markdown, templateId } = (e as CustomEvent).detail
  openNewUntitled()
  nextTick(() => {
    if (activeTab.value) {
      activeTab.value.content = markdown
      activeTab.value.name = `${templateId}-paper.md`
    }
  })
}

// ── Voice command handlers ─────────────────────────────────────────────
function handleVoiceSetMindmap() {
  workspaceMode.value = 'mindmap'
}

function handleVoiceExport(e: Event) {
  const { format } = (e as CustomEvent).detail
  if (format === 'word') handleExportWord()
  else if (format === 'pdf') handleExportPdf()
  else if (format === 'latex') handleExportLatex()
}

function handleVoiceAiPreset(e: Event) {
  const { action } = (e as CustomEvent).detail
  rightPanelTab.value = 'ai'
  nextTick(() => {
    aiPanelRef.value?.sendPreset(action)
  })
}

function handleVoiceCompliance() {
  runComplianceCheck()
}

function handleVoiceCitations() {
  handleProcessCitations()
}

function handleVoiceOpenFolder() {
  openWorkspaceFolder()
}

function handleVoiceNewFile() {
  openNewUntitled()
}

function handleVoiceSave() {
  saveFile()
}
</script>

<style scoped>
.editor-layout {
  display: flex;
  height: 100%;
  width: 100%;
  min-width: 0;
  overflow: hidden;
  background: var(--editor-bg);
  color: var(--text-primary);
}

/* -- Sidebar ------------------------------------------------ */
.layout-sidebar {
  position: relative;
  flex-shrink: 0;
  min-width: 0;
  overflow: hidden;
}
.layout-sidebar.collapsed {
  border-right: 1px solid var(--border-color);
  background: var(--sidebar-bg);
}
.sidebar-rail-button {
  position: absolute;
  left: 50%;
  top: 64px;
  transform: translateX(-50%) rotate(-90deg);
  transform-origin: center;
  padding: 6px 18px;
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 100px;
  background: var(--c-glass);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  color: var(--c-text-2);
  text-transform: uppercase;
  letter-spacing: 0.12em;
  font: inherit;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  white-space: nowrap;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  transition: all var(--motion-slow) var(--ease-spring);
}
.sidebar-rail-button:hover {
  color: var(--c-accent);
  background: var(--c-accent-soft);
  border-color: rgba(91, 108, 255, 0.2);
  box-shadow: 0 8px 24px rgba(91, 108, 255, 0.15);
  transform: translateX(-50%) rotate(-90deg) translateY(-2px);
}

/* -- Editor center ------------------------------------------ */
.layout-editor {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  container-type: inline-size;
}

/* -- Right panel -------------------------------------------- */
.layout-panel-wrapper {
  display: flex;
  align-items: stretch;
}
.layout-panel {
  flex: 0 1 auto;
  min-width: 260px;
  max-width: min(760px, 45vw);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.rp-content { flex: 1; min-height: 0; overflow: auto; }

/* -- Resize handle ------------------------------------------ */
.resize-handle {
  width: 8px;
  margin-left: -4px;
  margin-right: -4px;
  cursor: col-resize;
  background: transparent;
  position: relative;
  z-index: 10;
  flex-shrink: 0;
}
.resize-handle::after {
  content: '';
  position: absolute;
  top: 0; bottom: 0; left: 50%;
  width: 1px;
  background: var(--border-color);
  transition: all var(--motion-base) var(--ease-out);
  opacity: 0.3;
}
.resize-handle:hover::after,
.resize-handle:active::after {
  width: 2px;
  transform: translateX(-50%);
  background: var(--c-accent);
  opacity: 1;
  box-shadow: 0 0 8px var(--c-accent);
}

/* -- Responsive --------------------------------------------- */
@media (max-width: 1180px) {
  .layout-sidebar { width: 220px !important; }
  .layout-sidebar.collapsed { width: 44px !important; }
  .layout-panel { max-width: 42vw; }
}
@media (max-width: 980px) {
  .layout-sidebar, .sidebar-resize { display: none; }
  .layout-panel { width: min(420px, 46vw) !important; min-width: 320px; }
}
@media (max-width: 820px) {
  .layout-panel-wrapper { display: none; }
}
</style>
