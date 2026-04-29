<template>
  <div class="editor-layout">
    <!-- 左侧文件树 -->
    <div
      class="layout-sidebar"
      :class="{ collapsed: sidebarCollapsed }"
      :style="{ width: (sidebarCollapsed ? collapsedSidebarWidth : sidebarWidth) + 'px' }"
    >
      <button
        v-if="sidebarCollapsed"
        class="sidebar-collapse-toggle"
        title="展开 Explorer"
        @click="sidebarCollapsed = false"
      >
        <ChevronRight :size="14" :stroke-width="2" />
      </button>
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
        <EditorTabs />

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
          />

          <MonacoEditor
            :theme="isDark ? 'vs-dark' : 'vs'"
            :on-did-change-content="onDidChangeContent"
            @contentChange="onContentChange"
            @selectionChange="onSelectionChange"
          />
        </template>
      </template>
    </div>

    <!-- 右侧统一 Tab 面板 -->
    <template v-if="workspaceMode === 'editor' && activeTab && rightPanelTab">
      <div class="resize-handle panel-resize" @mousedown="startResize($event, 'panel')"></div>
      <div class="layout-panel" :style="{ width: panelWidth + 'px' }">
        <!-- Tab bar -->
        <div class="rp-tab-bar">
          <button class="rp-tab" :class="{ active: rightPanelTab === 'preview' }" @click="rightPanelTab = 'preview'">
            <Eye :size="13" :stroke-width="1.7" /> 预览
          </button>
          <button class="rp-tab" :class="{ active: rightPanelTab === 'ai' }" @click="rightPanelTab = 'ai'">
            <Bot :size="13" :stroke-width="1.7" /> AI 编辑
          </button>
          <button class="rp-tab" :class="{ active: rightPanelTab === 'argument' }" @click="rightPanelTab = 'argument'">
            <GitBranch :size="13" :stroke-width="1.7" /> 论证
          </button>
          <button class="rp-close" title="关闭面板" @click="rightPanelTab = null">
            <X :size="13" :stroke-width="2" />
          </button>
        </div>
        <!-- Tab content -->
        <MarkdownPreview
          v-if="rightPanelTab === 'preview'"
          :content="content"
          :version="contentVersion"
          class="rp-content"
        />
        <AiPanel
          v-if="rightPanelTab === 'ai'"
          :editor-context="selection.text || content"
          :can-undo="!!previousContent"
          :workspace-files="workspaceFiles"
          class="rp-content"
          @insert="handleInsert"
          @undo="handleUndo"
          @close="rightPanelTab = null"
        />
        <ArgumentMap v-if="rightPanelTab === 'argument'" class="rp-content" />
      </div>
    </template>

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
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'

// ── Layout sub-components ────────────────────────────────────────────────
import EditorWelcome from './EditorWelcome.vue'
import EditorToolbar from './EditorToolbar.vue'
import EditorNewProject from './EditorNewProject.vue'
import EditorCompliance from './EditorCompliance.vue'
import EditorTabs from './EditorTabs.vue'
import MonacoEditor from './MonacoEditor.vue'
import MarkdownPreview from './MarkdownPreview.vue'
import FileTree from './FileTree.vue'
import AiPanel from './AiPanel.vue'
import ArgumentMap from './ArgumentMap.vue'
import ComplianceModal from './ComplianceModal.vue'
import TemplatePicker from './TemplatePicker.vue'
import MindMapView from './MindMapView.vue'

// ── Icons ───────────────────────────────────────────────────────────────
import { Eye, Bot, GitBranch, X, ChevronRight } from './ui/icons'

// ── State composables ───────────────────────────────────────────────────
import { activeTab, content, contentVersion, selection, previousContent, tabs, aiResult, insertTextAtCursor } from '../composables/useEditorState'
import { useEditor } from '../composables/useEditor'
import { useEditorVision } from '../composables/useEditorVision'
import { useEditorCitation } from '../composables/useEditorCitation'
import { useEditorIO } from '../composables/useEditorIO'
import { useMindMap, mindMapToMarkdown, markdownToMindMapNodes } from '../composables/useMindMap'

const props = defineProps<{ isDark: boolean }>()

// ── Shared singleton state (single source of truth) ─────────────────────

// ── Tab / file operations ────────────────────────────────────────────────
const {
  openNewUntitled, setContent, markDirty,
  saveFile,
  onDidChangeContent, acceptGhostText, clearGhostText,
} = useEditor()

// ── AI edit actions (from useEditor, called once) ───────────────────────
const { aiEdit, applyAiResult, undoEdit } = useEditor()

// ── Feature composables ───────────────────────────────────────────────────
const { analyzeVision, uploadImage, insertImageFile } = useEditorVision()
const { processCitations, previewCitations, getZoteroStatus, searchZotero } = useEditorCitation()
const { exportToWord, exportLatex, exportPdf, loadExportTemplates } = useEditorIO()
const { resetMindMap, loadSavedMindMap, saveMindMap, addChild, updateNodeText } = useMindMap()

// ── Workspace mode ───────────────────────────────────────────────────────
const workspaceMode = ref<'editor' | 'mindmap'>('editor')
const sidebarCollapsed = ref(false)
const collapsedSidebarWidth = 44

// ── Right panel ──────────────────────────────────────────────────────────
type RightTab = 'preview' | 'ai' | 'argument'
const rightPanelTab = ref<RightTab | null>(null)
const toggleRightPanel = (tab: RightTab) => { rightPanelTab.value = rightPanelTab.value === tab ? null : tab }

// ── Export state ─────────────────────────────────────────────────────────
const exportTemplates = ref<{ id: string; name: string }[]>([])
const selectedTemplate = ref('')
const exportLoading = ref(false)
const exportMessage = ref('')
let exportToastTimer: ReturnType<typeof setTimeout> | null = null
const tectonicAvailable = ref(false)

// ── Compliance ────────────────────────────────────────────────────────────
const showCompliance = ref(false)
const complianceLoading = ref(false)
const complianceError = ref('')
const complianceReport = ref<Record<string, unknown> | null>(null)

// ── Template picker / project start ─────────────────────────────────────
const showTemplatePicker = ref(false)
const showProjectStart = ref(false)

const workspaceFiles = computed(() =>
  tabs.value.map(t => ({ name: t.name || t.path?.split(/[\\/]/).pop() || 'untitled', content: t.content }))
)

// ── Event handlers ──────────────────────────────────────────────────────

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
    if (activeTab.value && outline.trim()) setContent(outline)
  })
}

function openMindMapFromEditor() {
  sidebarCollapsed.value = true
  const md = content.value
  if (md.trim()) {
    const tree = markdownToMindMapNodes(md)
    if (tree) {
      resetMindMap(tree.text)
      const mm = useMindMap()
      const rootId = mm.draftMindMap.value.rootId
      for (const child of tree.children) {
        addChild(rootId)
        const newNodeId = mm.selectedNodeId.value
        updateNodeText(newNodeId, child.text)
        for (const grandChild of child.children) {
          addChild(newNodeId)
          updateNodeText(mm.selectedNodeId.value, grandChild.text)
        }
      }
      mm.selectNode(rootId)
    } else {
      loadSavedMindMap()
    }
  } else {
    loadSavedMindMap()
  }
  workspaceMode.value = 'mindmap'
}

async function handleSaveFile() {
  const err = await saveFile()
  showExportToast(err || 'Saved')
}

async function handleExportWord() {
  if (exportLoading.value) return
  exportLoading.value = true
  try {
    const title = (activeTab.value?.name || 'Scholar Assistant Export').replace(/\.md$/i, '')
    const err = await exportToWord(content.value, title)
    showExportToast(err || 'Word download started')
  } catch (e) { showExportToast(`Word export failed: ${e}`)
  } finally { exportLoading.value = false }
}

async function handleExportLatex() {
  if (!selectedTemplate.value || exportLoading.value) return
  if (!content.value.trim()) { showExportToast('Please write content first'); return }
  exportLoading.value = true
  try {
    const { tex, error } = await exportLatex(content.value, selectedTemplate.value)
    if (error) { showExportToast(error); return }
    if (tex) { await navigator.clipboard.writeText(tex); showExportToast('LaTeX copied to clipboard') }
    else showExportToast('Conversion result is empty')
  } catch (e) { showExportToast(`Export failed: ${e}`)
  } finally { exportLoading.value = false }
}

async function handleExportPdf() {
  if (!selectedTemplate.value || exportLoading.value) return
  if (!content.value.trim()) { showExportToast('Please write content first'); return }
  if (!tectonicAvailable.value) { showExportToast('Install Tectonic first'); return }
  exportLoading.value = true
  try {
    const title = (activeTab.value?.name || 'paper').replace(/\.md$/i, '')
    const err = await exportPdf(content.value, selectedTemplate.value, title)
    if (err === 'Cancelled') { showExportToast('Cancelled'); return }
    showExportToast(err || 'PDF saved')
  } catch (e) { showExportToast(`PDF export failed: ${e}`)
  } finally { exportLoading.value = false }
}

async function handleProcessCitations() {
  if (!content.value.trim()) { showExportToast('Please write content first'); return }
  try {
    const preview = await previewCitations(content.value)
    const data = await processCitations(content.value, [], 'ieee')
    if (!data?.text) { showExportToast('Citation indexing failed'); return }
    if (activeTab.value) { setContent(`${data.text}${data.bibliography || ''}`); markDirty() }
    showExportToast(`Indexed ${preview?.unique_count ?? data.citations?.length ?? 0} citations`)
  } catch (e) { showExportToast(`Citation indexing failed: ${e}`) }
}

async function handleZoteroInsert() {
  const query = window.prompt('Search Zotero')
  if (!query?.trim()) return
  try {
    const status = await getZoteroStatus()
    if (status && status.connected === false) { showExportToast('Configure Zotero API first'); return }
    const items = await searchZotero(query.trim(), 5)
    const item = items[0]
    if (!item?.key) { showExportToast('No Zotero result'); return }
    const citation = item.markdown_citation || (item.citation_key ? `[@${item.citation_key}]` : '')
    if (citation) insertTextAtCursor(citation)
    showExportToast(`Inserted ${item.citation_key || item.key}`)
  } catch (e) { showExportToast(`Zotero search failed: ${e}`) }
}

async function handleImageSelected(file: File) {
  try {
    const data = await insertImageFile(file)
    showExportToast(data ? 'Image inserted' : 'Image upload failed')
  } catch { showExportToast('Image upload failed') }
}

async function handleVisionSelected(file: File) {
  try {
    const data = await analyzeVision(file, 'general')
    if (!data) { showExportToast('Vision analysis failed'); return }
    const findings = data.key_findings?.length ? `\nFindings: ${data.key_findings.join('; ')}` : ''
    const chart = data.chart_type ? `\nChart type: ${data.chart_type}` : ''
    const table = data.table_data?.length
      ? `\n\n${data.table_data.map((row: string[]) => `| ${row.join(' | ')} |`).join('\n')}`
      : ''
    insertTextAtCursor(`\n\n> Vision: ${data.text || data.raw_description || 'No text returned'}${chart}${findings}${table}\n`)
    showExportToast('Vision result inserted')
  } catch (e) { showExportToast(`Vision analysis failed: ${e}`) }
}

async function runComplianceCheck() {
  if (!content.value.trim()) { complianceError.value = 'Editor content is empty'; showCompliance.value = true; return }
  complianceLoading.value = true
  complianceError.value = ''
  complianceReport.value = null
  showCompliance.value = true
  try {
    const resp = await fetch(`/api/compliance`, {
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
      complianceError.value = data.error || 'Compliance check failed'
    } else if (data.report?.summary) {
      complianceReport.value = data.report
    } else {
      complianceError.value = 'LLM returned unexpected format'
    }
  } catch (e) { complianceError.value = `请求失败: ${e}`
  } finally { complianceLoading.value = false }
}

function handleInsert(text: string) { aiResult.value = text; applyAiResult() }
function handleUndo() { undoEdit() }

function onContentChange(_value: string) {}
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

function showExportToast(msg: string) {
  if (exportToastTimer) clearTimeout(exportToastTimer)
  exportMessage.value = msg
  exportToastTimer = setTimeout(() => { exportMessage.value = '' }, 3000)
}

// ── Resize ───────────────────────────────────────────────────────────────
const sidebarWidth = ref(296)
const panelWidth = ref(300)

let _activeResizeMove: ((e: MouseEvent) => void) | null = null
let _activeResizeUp: (() => void) | null = null

function startResize(e: MouseEvent, target: 'sidebar' | 'panel') {
  e.preventDefault()
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
    _activeResizeMove = null; _activeResizeUp = null
  }
  _activeResizeMove = onMouseMove; _activeResizeUp = onMouseUp
  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', onMouseUp)
}

// ── Keyboard ─────────────────────────────────────────────────────────────
function onKeyDown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); handleSaveFile() }
  if (e.key === 'Tab' && !e.ctrlKey && !e.shiftKey && acceptGhostText()) { e.preventDefault() }
  if (e.key === 'Escape') clearGhostText()
}

// ── Lifecycle ─────────────────────────────────────────────────────────────
onMounted(() => {
  window.addEventListener('keydown', onKeyDown)
  loadExportTemplates().then(({ templates, tectonic_available }) => {
    exportTemplates.value = templates
    tectonicAvailable.value = tectonic_available
    if (templates.length && !selectedTemplate.value) selectedTemplate.value = templates[0].id
  })
  window.addEventListener('paper-scaffold', handlePaperScaffold as EventListener)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeyDown)
  window.removeEventListener('paper-scaffold', handlePaperScaffold as EventListener)
  if (_activeResizeMove) document.removeEventListener('mousemove', _activeResizeMove)
  if (_activeResizeUp) document.removeEventListener('mouseup', _activeResizeUp)
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

/* ── Sidebar ──────────────────────────────────────────────── */
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
.sidebar-collapse-toggle {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 5;
  width: 24px;
  height: 24px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--toolbar-bg);
  color: var(--c-text-3);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.sidebar-collapse-toggle:hover { color: var(--c-text-0); border-color: var(--c-accent); }
.sidebar-rail-button {
  position: absolute;
  left: 50%;
  top: 52px;
  transform: translateX(-50%);
  writing-mode: vertical-rl;
  border: 0;
  background: transparent;
  color: var(--c-text-3);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font: inherit;
  font-size: 11px;
  cursor: pointer;
}
.sidebar-rail-button:hover { color: var(--c-accent); }

/* ── Editor center ────────────────────────────────────────── */
.layout-editor {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  container-type: inline-size;
}

/* ── Right panel ──────────────────────────────────────────── */
.layout-panel {
  flex: 0 1 auto;
  min-width: 260px;
  max-width: min(760px, 45vw);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.rp-tab-bar {
  display: flex;
  align-items: center;
  background: var(--sidebar-bg);
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}
.rp-tab {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 36px;
  padding: 0 14px;
  border: none;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--c-text-3);
  font: inherit;
  font-size: var(--text-sm);
  cursor: pointer;
  transition: color var(--motion-fast), border-color var(--motion-fast), background var(--motion-fast);
}
.rp-tab:hover { color: var(--c-text-0); background: var(--hover-bg); }
.rp-tab.active { color: var(--c-accent); border-bottom-color: var(--c-accent); }
.rp-close {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  margin-right: 4px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--c-text-3);
  cursor: pointer;
}
.rp-close:hover { background: var(--hover-bg); color: var(--c-danger); }
.rp-content { flex: 1; min-height: 0; overflow: auto; }

/* ── Resize handle ────────────────────────────────────────── */
.resize-handle {
  width: 4px;
  cursor: col-resize;
  background: transparent;
  transition: background 0.15s;
  flex-shrink: 0;
}
.resize-handle:hover { background: var(--c-accent); }

/* ── Responsive ───────────────────────────────────────────── */
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
  .layout-panel, .panel-resize { display: none; }
}
</style>