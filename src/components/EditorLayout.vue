<template>
  <div class="editor-layout">
    <MindMapView v-if="workspaceMode === 'mindmap'" @enter-editor="enterEditorFromMindMap" />

    <template v-else>
      <EditorWelcome
        v-if="!activeTab"
        @new-project="showProjectStart = true"
        @open-template="showTemplatePicker = true"
        @open-folder="openWorkspaceFolder"
        @new-document="openNewUntitled"
        @open-recent="handleOpenRecentProject"
      />

      <template v-else>
        <AppHeader :title="activeTab.name" :subtitle="headerSubtitle" :icon="isLatexMode ? FileCode2 : FileText">
          <template #center>
            <SegmentedControl v-if="!isLatexMode" v-model="documentView" :options="documentViewOptions" :label="t('editor.documentView')" />
            <span v-else class="header-chapter">{{ t('editor.lineWordCount', { lines: lineCount, words: wordCount.toLocaleString() }) }}</span>
          </template>
          <StatusBadge tone="success" dot>{{ activeTab.isModified ? t('editor.unsavedChanges') : t('editor.autoSaved') }}</StatusBadge>
          <button type="button" class="header-action mode-toggle" @click="toggleEditorMode">{{ isLatexMode ? t('editor.writingView') : 'LaTeX' }}</button>
          <button type="button" class="header-action" @click="handleSaveFile"><Save :size="16" /> {{ t('editor.saveAction') }}</button>
          <button type="button" class="header-action primary" @click="isLatexMode ? aiPanelRef?.sendPreset('polish') : handleSelectionTask(t('editor.polish'))"><Sparkles :size="16" /> {{ t('editor.aiPolish') }}</button>
          <button type="button" class="header-icon" :title="sidebarCollapsed ? t('editor.fileTree') : t('editor.collapseSidebar')" @click="sidebarCollapsed = !sidebarCollapsed"><PanelLeftOpen v-if="sidebarCollapsed" :size="18" /><PanelLeftClose v-else :size="18" /></button>
          <button type="button" class="header-icon" :title="rightPanelVisible ? t('editor.collapseRight') : t('editor.expandRight')" @click="toggleHeaderRightPanel"><PanelRightClose :size="18" /></button>
          <button v-if="currentProject" type="button" class="header-icon" :title="t('project.closeProject')" @click="requestCloseProject"><FolderX :size="17" /></button>
        </AppHeader>

        <div class="editor-workbench" :class="{ 'latex-mode': isLatexMode, 'writing-mode': !isLatexMode, 'right-collapsed': !rightPanelVisible }">
          <div v-if="!sidebarCollapsed" class="workbench-left" :style="{ width: (isLatexMode ? 250 : 226) + 'px' }">
            <FileTree v-if="isLatexMode" @collapse="sidebarCollapsed = true" />
            <template v-else>
              <div class="sidebar-tabs">
                <button type="button" class="sidebar-tab" :class="{ active: writingSidebarTab === 'files' }" @click="writingSidebarTab = 'files'">{{ t('editor.files') }}</button>
                <button type="button" class="sidebar-tab" :class="{ active: writingSidebarTab === 'outline' }" @click="writingSidebarTab = 'outline'">{{ t('editor.outline') }}</button>
              </div>
              <FileTree v-if="writingSidebarTab === 'files'" @collapse="sidebarCollapsed = true" />
              <DocumentOutline v-else :content="content" :active-line="selection.startLine" @navigate="navigateToLine" @add="addSection" />
            </template>
          </div>

          <main class="workbench-center">
            <EditorTabs v-if="isLatexMode" />
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

            <div class="editor-surface">
              <MonacoEditor v-if="documentView === 'body' || isLatexMode" :theme="isDark ? 'vs-dark' : 'vs'" :presentation="isLatexMode ? 'code' : 'document'" @contentChange="onContentChange" @selectionChange="onSelectionChange" />
              <MarkdownPreview v-else-if="documentView === 'preview'" :content="content" :version="contentVersion" class="document-preview" />
              <DocumentOutline v-else class="central-outline" :content="content" :active-line="selection.startLine" @navigate="navigateToLine" @add="addSection" />

              <div v-if="selection.text && !isLatexMode" class="selection-toolbar">
                <button type="button" @click="handleSelectionTask(t('editor.polish'))"><Sparkles :size="14" /> {{ t('editor.polish') }}</button>
                <button type="button" @click="handleSelectionTask(t('editor.condense'))">{{ t('editor.condense') }}</button>
                <button type="button" @click="handleSelectionTask(t('editor.expand'))">{{ t('editor.expand') }}</button>
                <button type="button" @click="handleSelectionTask(t('editor.checkArgument'))">{{ t('editor.checkArgument') }}</button>
              </div>
            </div>
          </main>

          <aside v-if="rightPanelVisible" class="workbench-right" :style="{ width: (isLatexMode ? 340 : 356) + 'px' }">
            <EditorRightTabBar
              :model-value="rightPanelTab"
              :agent-mode="!isLatexMode"
              @update:model-value="setRightPanelTab"
            />
            <MarkdownPreview v-if="rightPanelTab === 'preview'" :content="content" :version="contentVersion" class="rp-content rp-preview" />
            <CompanionPanel v-else-if="rightPanelTab === 'argument'" :content="content" class="rp-content" />
            <template v-else>
              <AiPanel v-if="isLatexMode" ref="aiPanelRef" workspace-variant :editor-context="selection.text || content" :active-file="activeFile" :can-undo="!!previousContent" :workspace-files="workspaceFiles" class="rp-content" @insert="handleInsert" @undo="handleUndo" @close="rightPanelVisible = false" />
              <TaskAgentPanel v-else :context="content" :selection="selection.text" :active-file="activeFile" />
            </template>
          </aside>
        </div>
      </template>
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
      @project-created="handleProjectCreated"
    />

    <AppConfirmDialog
      v-model="showCloseProjectConfirm"
      :title="t('project.closeProject')"
      :description="t('editor.closeProjectDescription')"
      :detail="hasDirtyTabs ? t('editor.closeProjectDirtyDetail') : t('editor.closeProjectDetail')"
      :confirm-label="t('project.closeProject')"
      :cancel-label="t('general.cancel')"
      :tone="hasDirtyTabs ? 'danger' : 'default'"
      @confirm="performCloseProject"
    />

    <AppPromptDialog
      v-model="showZoteroPrompt"
      :title="t('editor.searchZotero')"
      :description="t('editor.zoteroSearchDescription')"
      :label="t('general.search')"
      :placeholder="t('editor.zoteroSearchPlaceholder')"
      :confirm-label="t('general.search')"
      :cancel-label="t('general.cancel')"
      :error="zoteroPromptError"
      :busy="zoteroSearching"
      @submit="submitZoteroSearch"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, defineAsyncComponent, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

// -- Layout sub-components ------------------------------------------------
import EditorWelcome from './EditorWelcome.vue'
import EditorToolbar from './EditorToolbar.vue'
import EditorNewProject from './EditorNewProject.vue'
import EditorCompliance from './EditorCompliance.vue'
import EditorTabs from './EditorTabs.vue'
import EditorRightTabBar from './EditorRightTabBar.vue'
import FileTree from './FileTree.vue'
import TemplatePicker from './TemplatePicker.vue'
import DocumentOutline from './DocumentOutline.vue'
import TaskAgentPanel from './TaskAgentPanel.vue'
import AppHeader from './shell/AppHeader.vue'
import AppConfirmDialog from './shell/AppConfirmDialog.vue'
import AppPromptDialog from './shell/AppPromptDialog.vue'
import SegmentedControl from './shell/SegmentedControl.vue'
import StatusBadge from './shell/StatusBadge.vue'
import { FileCode2, FileText, FolderX, PanelLeftClose, PanelLeftOpen, PanelRightClose, Save, Sparkles } from 'lucide-vue-next'

// -- State composables ---------------------------------------------------
import { useEditorState, getRange } from '../composables/useEditorState'
import { useEditor } from '../composables/useEditor'
import { useEditorVision } from '../composables/useEditorVision'
import { useToast } from '../composables/useToast'
import { useEditorCitation } from '../composables/useEditorCitation'
import { useEditorIO } from '../composables/useEditorIO'
import { useMindMap, markdownToMindMapNodes } from '../composables/useMindMap'
import { useFileTree } from '../composables/useFileTree'
import { useArgumentCompanion } from '../composables/useArgumentCompanion'
import { useAgentChat } from '../composables/useAgentChat'
import { API_BASE } from '../utils/api'
import { closeProject, currentProject, useProject } from '../composables/useProject'
import { open as openDialog } from '@tauri-apps/plugin-dialog'

const MonacoEditor = defineAsyncComponent(() => import('./MonacoEditor.vue'))
const MarkdownPreview = defineAsyncComponent(() => import('./MarkdownPreview.vue'))
const MindMapView = defineAsyncComponent(() => import('./MindMapView.vue'))
const AiPanel = defineAsyncComponent(() => import('./AiPanel.vue'))
const CompanionPanel = defineAsyncComponent(() => import('./argument/CompanionPanel.vue'))

defineProps<{ isDark: boolean }>()

// -- Shared singleton state (single source of truth) ---------------------
const { activeTab, activeTabId, content, contentVersion, selection, previousContent, tabs, aiResult, insertTextAtCursor, activeFile, monacoEditor } = useEditorState()

// -- Tab / file operations ------------------------------------------------
const {
  openNewUntitled, openFile, setContent, markDirty,
  saveFile, reloadOpenTabs,
} = useEditor()

// -- AI edit actions (from useEditor, called once) -----------------------
const { applyAiResult, undoEdit } = useEditor()

// -- Feature composables ---------------------------------------------------
const { analyzeVision, insertImageFile } = useEditorVision()
const { processCitations, previewCitations, getZoteroStatus, searchZotero } = useEditorCitation()
const { exportToWord, exportLatex, exportPdf, loadExportTemplates, saveBlob } = useEditorIO()
const { resetMindMap, loadSavedMindMap, saveMindMap, addChild, updateNodeText, updateNodeBody, skipNextBackendLoad } = useMindMap()
const { readFileContent, refresh: refreshFileTree, rootDir } = useFileTree()
const { sendMessage: sendAgentMessage } = useAgentChat()

// -- Workspace mode -------------------------------------------------------
const workspaceMode = ref<'editor' | 'mindmap'>('editor')
const showZoteroPrompt = ref(false)
const zoteroSearching = ref(false)
const zoteroPromptError = ref('')
let _contentBeforeMindMap = ''
const sidebarCollapsed = ref(false)
const writingSidebarTab = ref<'files' | 'outline'>('files')
const collapsedSidebarWidth = 44
const documentView = ref<'body' | 'outline' | 'preview'>('body')
const rightPanelVisible = ref(true)
const editorModeOverride = ref<'auto' | 'writing' | 'latex'>('auto')
const isLatexMode = computed(() => editorModeOverride.value === 'latex'
  || (editorModeOverride.value === 'auto' && /\.tex$/i.test(activeTab.value?.name || activeTab.value?.path || '')))
const lineCount = computed(() => content.value ? content.value.split(/\r?\n/).length : 0)
const wordCount = computed(() => {
  const latin = content.value.match(/[A-Za-z0-9]+/g)?.length || 0
  const chinese = content.value.match(/[\u3400-\u9fff]/g)?.length || 0
  return latin + chinese
})
const headerSubtitle = computed(() => t(isLatexMode.value ? 'editor.latexHeaderSubtitle' : 'editor.writingHeaderSubtitle', {
  status: activeTab.value?.isModified ? t('editor.notSaved') : t('editor.saved'),
}))
const documentViewOptions = computed(() => [
  { value: 'body', label: t('editor.body') },
  { value: 'outline', label: t('editor.outline') },
  { value: 'preview', label: t('editor.preview') },
])
watch(workspaceMode, mode => {
  window.dispatchEvent(new CustomEvent('shell-section-change', { detail: mode === 'mindmap' ? 'mindmap' : 'write' }))
})
watch(isLatexMode, () => { documentView.value = 'body' })

// -- Right panel ----------------------------------------------------------
type RightTab = 'preview' | 'ai' | 'argument'
const rightPanelTab = ref<RightTab | null>('ai')
const aiPanelRef = ref<InstanceType<typeof AiPanel> | null>(null)
const toggleRightPanel = (tab: RightTab) => {
  rightPanelTab.value = tab
  rightPanelVisible.value = true
}
const setRightPanelTab = (tab: RightTab | null) => {
  if (tab === null) {
    rightPanelVisible.value = false
    rightPanelTab.value = null
    return
  }
  toggleRightPanel(tab)
}
const toggleHeaderRightPanel = () => {
  if (rightPanelVisible.value) {
    rightPanelVisible.value = false
    return
  }
  if (rightPanelTab.value === null) rightPanelTab.value = 'ai'
  rightPanelVisible.value = true
}

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
const showCloseProjectConfirm = ref(false)
const hasDirtyTabs = computed(() => tabs.value.some(tab => tab.isModified))

function requestCloseProject() {
  showCloseProjectConfirm.value = true
}

async function performCloseProject() {
  await closeProject()
  tabs.value = []
  activeTabId.value = null
  workspaceMode.value = 'editor'
  showCloseProjectConfirm.value = false
}

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

function navigateToLine(line: number) {
  documentView.value = 'body'
  nextTick(() => {
    monacoEditor.value?.revealLineInCenter(line)
    monacoEditor.value?.setPosition({ lineNumber: line, column: 1 })
    monacoEditor.value?.focus()
  })
}

function toggleEditorMode() {
  editorModeOverride.value = isLatexMode.value ? 'writing' : 'latex'
  documentView.value = 'body'
}

function addSection() {
  insertTextAtCursor(`${content.value.endsWith('\n') ? '' : '\n'}\n## ${t('editor.newSection')}\n\n`)
}

async function handleSelectionTask(action: string) {
  const target = selection.value.text || content.value
  if (!target.trim()) return
  // Auto-open the right panel so the user sees the agent working (writing mode)
  if (!isLatexMode.value) {
    rightPanelTab.value = 'ai'
    rightPanelVisible.value = true
  }
  await sendAgentMessage(
    t('editor.selectionTaskPrompt', { action, target: selection.value.text ? t('editor.selectedText') : t('editor.documentTarget') }),
    target,
    '',
    rootDir.value || undefined,
    activeFile.value || undefined,
  )
}

function handleShellWorkspaceMode(event: Event) {
  const mode = (event as CustomEvent).detail
  if (mode === 'mindmap') {
    if (workspaceMode.value === 'mindmap') {
      sidebarCollapsed.value = true
      return
    }
    openMindMapFromEditor()
  }
  else if (mode === 'editor') workspaceMode.value = 'editor'
}

async function openWorkspaceFolder() {
  try {
    const selected = await openDialog({ directory: true, multiple: false })
    if (selected) {
      window.dispatchEvent(new CustomEvent('open-workspace-folder', { detail: { path: selected } }))
      // Auto-detect and load project metadata if available
      const isProject = await useProject().detectProject(selected as string)
      if (isProject) {
        try { await useProject().openProject(selected as string) } catch { /* */ }
      }
    }
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

const { danger } = useToast()

function _mainMdPath(projectPath: string): string {
  // Normalize backslashes from Python backend (Windows) to forward slashes,
  // matching Tauri plugin-fs output format, so readFileContent resolves correctly.
  return projectPath.replace(/\\/g, '/') + '/draft/main.md'
}

async function _openProjectAndMainMd(path: string) {
  await useProject().openProject(path)
  const mainMd = _mainMdPath(path)
  try {
    const text = await readFileContent(mainMd)
    openFile(mainMd, text)
    nextTick(() => openMindMapFromEditor())
  } catch (e) {
    console.error('[EditorLayout] Failed to open main.md:', e)
    openNewUntitled()
  }
}

async function handleProjectCreated(path: string) {
  showProjectStart.value = false
  try {
    await _openProjectAndMainMd(path)
  } catch (e: any) {
    danger(e.message || t('project.openFailed'))
  }
}

async function handleOpenRecentProject(path: string) {
  try {
    await _openProjectAndMainMd(path)
  } catch (e: any) {
    danger(e.message || t('editor.openRecentFailed'))
  }
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

async function openMindMapFromEditor() {
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
  if (md.trim()) {
    const { useMindMapLayout } = await import('../composables/useMindMapLayout')
    useMindMapLayout().autoLayout('radial')
  }
  workspaceMode.value = 'mindmap'
}

async function handleSaveFile() {
  const err = await saveFile()
  showExportToast(err || t('editor.saved'))
}

function _extractTitle(): string {
  const m = content.value.match(/^#\s+(.+)$/m)
  if (m) return m[1].trim()
  return (activeTab.value?.name || 'paper').replace(/\.md$/i, '')
}

async function handleExportWord() {
  if (exportLoading.value) return
  exportLoading.value = true
  try {
    const title = _extractTitle()
    const err = await exportToWord(content.value, title)
    showExportToast(err || t('editor.wordExportStarted'))
  } catch (e) { showExportToast(t('editor.wordExportFailed', { msg: String(e) }))
  } finally { exportLoading.value = false }
}

async function handleExportLatex() {
  if (exportLoading.value) return
  if (!selectedTemplate.value) { showExportToast(t('editor.selectTemplate')); return }
  if (!content.value.trim()) { showExportToast(t('editor.pleaseInputContent')); return }
  exportLoading.value = true
  try {
    const { tex, error } = await exportLatex(content.value, selectedTemplate.value)
    if (error) { showExportToast(error); return }
    if (tex) {
      const title = _extractTitle()
      const blob = new Blob([tex], { type: 'text/x-tex;charset=utf-8' })
      const saveErr = await saveBlob(blob, `${title}.tex`)
      if (saveErr === 'Cancelled') { showExportToast(t('editor.cancelled')); return }
      showExportToast(saveErr || t('editor.latexSaved', 'LaTeX saved'))
    }
    else showExportToast(t('editor.conversionEmpty'))
  } catch (e) { showExportToast(t('editor.exportFailed', { msg: String(e) }))
  } finally { exportLoading.value = false }
}

async function handleExportPdf() {
  if (exportLoading.value) return
  if (!selectedTemplate.value) { showExportToast(t('editor.selectTemplate')); return }
  if (!content.value.trim()) { showExportToast(t('editor.pleaseInputContent')); return }
  if (!tectonicAvailable.value) {
    const { tectonic_available } = await loadExportTemplates()
    tectonicAvailable.value = tectonic_available
    if (!tectonic_available) { showExportToast(t('editor.installTectonic')); return }
  }
  exportLoading.value = true
  try {
    const title = _extractTitle()
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
  zoteroPromptError.value = ''
  showZoteroPrompt.value = true
}

async function submitZoteroSearch(query: string) {
  zoteroSearching.value = true
  zoteroPromptError.value = ''
  try {
    const status = await getZoteroStatus()
    if (status && status.connected === false) {
      zoteroPromptError.value = t('editor.zoteroConfig')
      return
    }
    const items = await searchZotero(query, 5)
    const item = items[0]
    if (!item?.key) {
      zoteroPromptError.value = t('editor.zoteroNotFound')
      return
    }
    const citation = item.markdown_citation || (item.citation_key ? `[@${item.citation_key}]` : '')
    if (citation) insertTextAtCursor(citation)
    showExportToast(t('editor.zoteroInserted', { key: item.citation_key || item.key }))
    showZoteroPrompt.value = false
  } catch (e) {
    zoteroPromptError.value = t('editor.zoteroFailed', { msg: String(e) })
  } finally {
    zoteroSearching.value = false
  }
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

function handleVoiceStop(_text: string) {
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
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'b') {
    e.preventDefault()
    sidebarCollapsed.value = !sidebarCollapsed.value
  }
}

// -- Lifecycle -------------------------------------------------------------
onMounted(() => {
  window.addEventListener('keydown', onKeyDown)
  window.addEventListener('shell-workspace-mode', handleShellWorkspaceMode)
  loadExportTemplates().then(({ templates, tectonic_available }) => {
    exportTemplates.value = templates
    tectonicAvailable.value = tectonic_available
    if (templates.length && !selectedTemplate.value) selectedTemplate.value = templates[0].id
  })
  window.addEventListener('paper-scaffold', handlePaperScaffold as EventListener)
  window.addEventListener('agent-files-changed', handleAgentFileChange as EventListener)

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
  window.removeEventListener('shell-workspace-mode', handleShellWorkspaceMode)
  window.removeEventListener('paper-scaffold', handlePaperScaffold as EventListener)
  window.removeEventListener('agent-files-changed', handleAgentFileChange as EventListener)
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
  openMindMapFromEditor()
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

async function handleAgentFileChange() {
  await reloadOpenTabs()
  await refreshFileTree()
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

/* Reference-driven workbench overrides */
.editor-layout {
  flex-direction: column;
  background: var(--c-app-bg);
}
.editor-layout > :deep(.mindmap-view),
.editor-layout > :deep(.editor-welcome) { flex: 1; min-height: 0; }
.editor-workbench {
  flex: 1;
  min-height: 0;
  min-width: 0;
  display: flex;
  overflow: hidden;
  background: var(--c-panel);
}
.workbench-left {
  flex: 0 0 auto;
  min-width: 176px;
  min-height: 0;
  overflow: hidden;
  background: var(--c-panel);
  display: flex;
  flex-direction: column;
}

.sidebar-tabs {
  display: flex;
  gap: 2px;
  padding: 4px 8px;
  border-bottom: 1px solid var(--c-surface-3);
  flex-shrink: 0;
}

.sidebar-tab {
  flex: 1;
  padding: 4px 8px;
  border: none;
  background: none;
  border-radius: 5px;
  font-size: 11px;
  font-weight: 500;
  color: var(--c-text-3);
  cursor: pointer;
  transition: color 0.15s ease, background 0.15s ease;
}
.sidebar-tab:hover { color: var(--c-text-1); background: var(--c-surface-2); }
.sidebar-tab.active { color: var(--c-accent); background: var(--c-accent-soft); }
.workbench-center {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  border-left: 0;
  background: var(--c-panel);
}
.workbench-right {
  flex: 0 0 auto;
  min-width: 300px;
  min-height: 0;
  overflow: hidden;
  background: var(--c-panel);
  display: flex;
  flex-direction: column;
  border-left: 1px solid var(--c-border);
}
.editor-surface {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  background: var(--c-panel);
}
.editor-surface > :deep(.monaco-wrapper),
.editor-surface > :deep(.document-preview),
.editor-surface > :deep(.central-outline) { height: 100%; }
.document-preview { max-width: none; padding: 42px clamp(28px, 5vw, 80px); overflow: auto; }
.central-outline { max-width: 760px; margin: 24px auto; border: 1px solid var(--c-border); border-radius: 10px; overflow: hidden; }
.header-chapter { color: var(--c-text-2); font-size: 12px; }
.header-action, .header-icon {
  height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding: 0 12px;
  border: 1px solid var(--c-border);
  border-radius: 8px;
  background: var(--c-panel);
  color: var(--c-text-1);
  font: 500 12px/1 var(--font-sans), var(--font-zh);
  cursor: pointer;
}
.header-icon { width: 36px; padding: 0; }
.header-action:hover, .header-icon:hover { background: var(--c-surface-2); color: var(--c-text-0); }
.header-action.primary { border-color: var(--c-accent); background: var(--c-accent); color: #fff; }
.selection-toolbar {
  position: absolute;
  z-index: 20;
  top: 18px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 5px;
  border: 1px solid var(--c-border);
  border-radius: 9px;
  background: var(--c-panel);
  box-shadow: 0 7px 22px rgba(50, 43, 31, .12);
}
.selection-toolbar button { height: 29px; display: inline-flex; align-items: center; gap: 5px; padding: 0 9px; border: 0; border-radius: 6px; background: transparent; color: var(--c-text-1); font-size: 11px; cursor: pointer; }
.selection-toolbar button:hover { color: var(--c-accent); background: var(--c-accent-soft); }
.writing-mode :deep(.editor-toolbar), .latex-mode :deep(.editor-toolbar) { flex: 0 0 auto; border-color: var(--c-border); background: var(--c-panel); box-shadow: none; }
.writing-mode :deep(.editor-tabs) { display: none; }
.latex-mode :deep(.editor-tabs) { border-color: var(--c-border); background: var(--c-panel); }

@media (max-width: 1180px) {
  .workbench-left { width: 208px !important; }
  .workbench-right { width: 332px !important; min-width: 300px; }
}
@media (max-width: 980px) {
  .workbench-left { width: 190px !important; }
  .header-action:not(.primary) { display: none; }
  .editor-workbench { position: relative; }
  .workbench-right { position: absolute; z-index: 35; top: 0; right: 0; bottom: 0; width: min(356px, calc(100% - 56px)) !important; box-shadow: var(--elevation-3); }
}
@media (max-width: 760px) {
  .workbench-left { display: none; }
  .header-action.primary { display: none; }
  .header-icon { display: none; }
}
</style>
