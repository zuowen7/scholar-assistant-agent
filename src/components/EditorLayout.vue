<template>
  <div class="editor-layout">
    <MindMapView v-if="draftView === 'mindmap'" @enter-editor="enterEditorFromMindMap" />

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
        <AppHeader
          :title="activeTab.name"
          :subtitle="headerSubtitle"
          :icon="isLatexMode ? FileCode2 : FileText"
          :compact="rightDock === 'agent'"
        >
          <template #title-after>
            <!-- 仅未保存时显示警示；"已自动保存"由右下角 3 秒 toast 反馈，不常驻 -->
            <StatusBadge v-if="activeTab.isModified" tone="warning" dot>{{
              t('editor.unsavedChanges')
            }}</StatusBadge>
          </template>
          <template #center>
            <SegmentedControl
              v-if="!isLatexMode"
              v-model="documentView"
              :options="documentViewOptions"
              :label="t('editor.documentView')"
            />
            <span v-else class="header-chapter">{{
              t('editor.lineWordCount', { lines: lineCount, words: wordCount.toLocaleString() })
            }}</span>
          </template>
          <button type="button" class="header-action mode-toggle" @click="toggleEditorMode">
            {{ isLatexMode ? t('editor.writingView') : 'LaTeX' }}
          </button>
          <button type="button" class="header-action" @click="handleSaveFile">
            <Save :size="16" /> {{ t('editor.saveAction') }}
          </button>
          <UiButton variant="primary" size="sm" @click="navigate('export')">
            {{ t('editor.exportLabel') }}
          </UiButton>
          <button
            type="button"
            class="header-icon"
            :title="sidebarCollapsed ? t('editor.fileTree') : t('editor.collapseSidebar')"
            @click="sidebarCollapsed = !sidebarCollapsed"
          >
            <PanelLeftOpen v-if="sidebarCollapsed" :size="18" /><PanelLeftClose v-else :size="18" />
          </button>
          <button
            type="button"
            class="header-icon"
            :title="rightDock === 'agent' ? t('editor.collapseRight') : t('editor.expandRight')"
            @click="toggleAgentDock()"
          >
            <PanelRightClose :size="18" />
          </button>
          <button
            v-if="currentProject"
            type="button"
            class="header-icon"
            :title="t('project.closeProject')"
            @click="requestCloseProject"
          >
            <FolderX :size="17" />
          </button>
        </AppHeader>

        <div
          class="editor-workbench"
          :class="{
            'latex-mode': isLatexMode,
            'writing-mode': !isLatexMode,
            'right-collapsed': !rightPanelVisible,
          }"
        >
          <div
            v-if="!sidebarCollapsed"
            class="workbench-left"
            :style="{ width: (isLatexMode ? 250 : 226) + 'px' }"
          >
            <FileTree v-if="isLatexMode" @collapse="sidebarCollapsed = true" />
            <template v-else>
              <div class="sidebar-tabs">
                <button
                  type="button"
                  class="sidebar-tab"
                  :class="{ active: writingSidebarTab === 'files' }"
                  @click="writingSidebarTab = 'files'"
                >
                  {{ t('editor.files') }}
                </button>
                <button
                  type="button"
                  class="sidebar-tab"
                  :class="{ active: writingSidebarTab === 'outline' }"
                  @click="writingSidebarTab = 'outline'"
                >
                  {{ t('editor.outline') }}
                </button>
              </div>
              <FileTree v-if="writingSidebarTab === 'files'" @collapse="sidebarCollapsed = true" />
              <DocumentOutline
                v-else
                :content="content"
                :active-line="selection.startLine"
                @navigate="navigateToLine"
                @add="addSection"
              />
            </template>
          </div>

          <main class="workbench-center">
            <EditorTabs @request-close="requestCloseTab" />
            <EditorToolbar
              ref="toolbarRef"
              :active-right-tab="rightPanelTab"
              :agent-open="rightDock === 'agent'"
              :message="exportMessage"
              @toggle-right="toggleRightPanel"
              @image-selected="handleImageSelected"
              @vision-selected="handleVisionSelected"
              @insert-table="insertTable"
              @insert-inline-formula="insertInlineFormula"
              @insert-block-formula="insertBlockFormula"
              @run-compliance="runComplianceCheck"
              @process-citations="handleProcessCitations"
              @zotero-insert="handleZoteroInsert"
              @voice-start="handleVoiceStart"
              @voice-update="handleVoiceUpdate"
              @voice-stop="handleVoiceStop"
            />

            <div class="editor-surface">
              <MonacoEditor
                v-if="documentView === 'body' || isLatexMode"
                :theme="isDark ? 'vs-dark' : 'vs'"
                :presentation="isLatexMode ? 'code' : 'document'"
                @content-change="onContentChange"
                @selection-change="onSelectionChange"
                @selection-action="handleSelectionTask"
              />
              <MarkdownPreview
                v-else-if="documentView === 'preview'"
                :content="content"
                :version="contentVersion"
                class="document-preview"
              />
              <DocumentOutline
                v-else
                class="central-outline"
                :content="content"
                :active-line="selection.startLine"
                @navigate="navigateToLine"
                @add="addSection"
              />
            </div>
          </main>

          <aside
            v-if="rightPanelVisible"
            class="workbench-right"
            :style="{ width: (isLatexMode ? 340 : 356) + 'px' }"
          >
            <EditorRightTabBar
              :model-value="rightPanelTab"
              :agent-open="rightDock === 'agent'"
              @update:model-value="setRightPanelTab"
              @open-agent="toggleAgentDock(true)"
            />
            <MarkdownPreview
              v-if="rightPanelTab === 'preview'"
              :content="content"
              :version="contentVersion"
              class="rp-content rp-preview"
            />
            <CompanionPanel v-else :content="content" class="rp-content" />
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
      :is-dark="isDark"
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

    <AppConfirmDialog
      v-model="showCloseDocumentConfirm"
      :title="t('editor.closeCurrentDocument')"
      :description="t('editor.closeDocumentDescription')"
      :detail="t('editor.closeDocumentDirtyDetail')"
      :confirm-label="t('editor.closeCurrentDocument')"
      :cancel-label="t('general.cancel')"
      tone="danger"
      @confirm="performCloseCurrentDocument"
    />

    <AppPromptDialog
      v-model="showZoteroPrompt"
      :title="t('editor.searchZotero')"
      :description="
        zoteroMode === 'local' ? t('editor.zoteroLocalHint') : t('editor.zoteroSearchDescription')
      "
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
import {
  ref,
  computed,
  defineAsyncComponent,
  watch,
  onMounted,
  onBeforeUnmount,
  nextTick,
} from 'vue'
import { useI18n } from 'vue-i18n'
import type { ComplianceReport } from '../types'

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
import AppHeader from './shell/AppHeader.vue'
import AppConfirmDialog from './shell/AppConfirmDialog.vue'
import AppPromptDialog from './shell/AppPromptDialog.vue'
import SegmentedControl from './shell/SegmentedControl.vue'
import StatusBadge from './shell/StatusBadge.vue'
import UiButton from './ui/UiButton.vue'
import {
  FileCode2,
  FileText,
  FolderX,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  Save,
} from 'lucide-vue-next'

// -- State composables ---------------------------------------------------
import { useEditorState, getRange } from '../composables/useEditorState'
import { useEditor } from '../composables/useEditor'
import { useEditorVision } from '../composables/useEditorVision'
import type { VisionAnalysisType, VisionAnalysisResponse } from '../composables/useEditorVision'
import { useToast } from '../composables/useToast'
import { useEditorCitation } from '../composables/useEditorCitation'
import { useExportWorkspace } from '../composables/useExportWorkspace'
import { useMindMap, markdownToMindMapNodes } from '../composables/useMindMap'
import { useFileTree } from '../composables/useFileTree'
import { useArgumentCompanion } from '../composables/useArgumentCompanion'
import { useAgentChat } from '../composables/useAgentChat'
import { useWorkspaceNavigation } from '../composables/useWorkspaceNavigation'
import { useProjectWorkspace } from '../composables/useProjectWorkspace'
import { API_BASE } from '../utils/api'
import { closeProject, currentProject, useProject } from '../composables/useProject'
import { open as openDialog } from '@tauri-apps/plugin-dialog'

const MonacoEditor = defineAsyncComponent(() => import('./MonacoEditor.vue'))
const MarkdownPreview = defineAsyncComponent(() => import('./MarkdownPreview.vue'))
const MindMapView = defineAsyncComponent(() => import('./MindMapView.vue'))
const CompanionPanel = defineAsyncComponent(() => import('./argument/CompanionPanel.vue'))

defineProps<{ isDark: boolean }>()

// -- Shared singleton state (single source of truth) ---------------------
const {
  activeTab,
  activeTabId,
  content,
  contentVersion,
  selection,
  tabs,
  insertTextAtCursor,
  activeFile,
  monacoEditor,
} = useEditorState()

// -- Tab / file operations ------------------------------------------------
const { openNewUntitled, closeTab, setContent, markDirty, saveFile, reloadOpenTabs } = useEditor()

// -- Feature composables ---------------------------------------------------
const {
  analyzeVision,
  insertImageFile,
  ocrImage,
  analyzeChart,
  extractTableFromImage,
  recognizeFormula,
} = useEditorVision()
const { processCitations, previewCitations, getZoteroStatus, searchZotero } = useEditorCitation()
const {
  resetMindMap,
  hasSavedMindMap,
  loadSavedMindMap,
  loadFromBackend,
  saveMindMap,
  addChild,
  updateNodeText,
  updateNodeBody,
  skipNextBackendLoad,
} = useMindMap()
const { refresh: refreshFileTree, rootDir } = useFileTree()
const { sendMessage: sendAgentMessage } = useAgentChat()
const { draftView, rightDock, setDraftView, toggleAgentDock, navigate } = useWorkspaceNavigation()
const exportWorkspace = useExportWorkspace()
const { openProjectWorkspace } = useProjectWorkspace()

// -- Workspace mode -------------------------------------------------------
const showZoteroPrompt = ref(false)
const zoteroSearching = ref(false)
const zoteroPromptError = ref('')
const zoteroMode = ref<'cloud' | 'local' | 'unavailable' | null>(null)
let _contentBeforeMindMap = ''
const sidebarCollapsed = ref(false)
const writingSidebarTab = ref<'files' | 'outline'>('files')
const documentView = computed<'body' | 'outline' | 'preview' | 'mindmap'>({
  get: () =>
    draftView.value === 'mindmap'
      ? 'mindmap'
      : draftView.value === 'preview'
        ? 'preview'
        : draftView.value === 'outline'
          ? 'outline'
          : 'body',
  set: (view) => {
    if (view === 'mindmap') {
      void openMindMapFromEditor()
      return
    }
    setDraftView(view === 'body' ? 'editor' : view)
  },
})
const rightPanelVisible = ref(false)
const isLatexMode = computed(() => draftView.value === 'latex')
const lineCount = computed(() => (content.value ? content.value.split(/\r?\n/).length : 0))
const wordCount = computed(() => {
  const latin = content.value.match(/[A-Za-z0-9]+/g)?.length || 0
  const chinese = content.value.match(/[\u3400-\u9fff]/g)?.length || 0
  return latin + chinese
})
const headerSubtitle = computed(() => {
  // 仅在未保存时提示；已保存状态由自动保存 toast（3 秒自动消失）反馈，
  // 不再常驻显示"已保存"这类装饰性文案
  const status = activeTab.value?.isModified ? ` · ${t('editor.notSaved')}` : ''
  return t(isLatexMode.value ? 'editor.latexHeaderSubtitle' : 'editor.writingHeaderSubtitle', {
    status,
  })
})
const documentViewOptions = computed(() => [
  { value: 'body', label: t('editor.body') },
  { value: 'preview', label: t('editor.preview') },
  { value: 'mindmap', label: t('editor.mindMap') },
])
watch(
  () => activeTab.value?.path || activeTab.value?.name || '',
  (path) => {
    if (/\.tex$/i.test(path)) setDraftView('latex')
    else if (draftView.value === 'latex') setDraftView('editor')
  },
  { immediate: true },
)

// -- Right panel ----------------------------------------------------------
type RightTab = 'preview' | 'argument'
type RightPanelCommand = RightTab | 'agent'
const rightPanelTab = ref<RightTab | null>('preview')
const toggleRightPanel = (tab: RightPanelCommand) => {
  if (tab === 'agent') {
    toggleAgentDock(true)
    rightPanelVisible.value = false
    return
  }
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
// -- Export state ---------------------------------------------------------
const exportMessage = ref('')
const toolbarRef = ref<InstanceType<typeof EditorToolbar> | null>(null)
let exportToastTimer: ReturnType<typeof setTimeout> | null = null

// -- Compliance ------------------------------------------------------------
const showCompliance = ref(false)
const complianceLoading = ref(false)
const complianceError = ref('')
const complianceReport = ref<ComplianceReport | null>(null)

// -- Template picker / project start -------------------------------------
const showTemplatePicker = ref(false)
const showProjectStart = ref(false)
const showCloseProjectConfirm = ref(false)
const showCloseDocumentConfirm = ref(false)
const pendingCloseTabId = ref<string | null>(null)
const hasDirtyTabs = computed(() => tabs.value.some((tab) => tab.isModified))

function requestCloseTab(tabId: string) {
  const tab = tabs.value.find((candidate) => candidate.id === tabId)
  if (!tab) return
  if (tab.isModified) {
    pendingCloseTabId.value = tabId
    showCloseDocumentConfirm.value = true
    return
  }
  closeTab(tabId)
}

function performCloseCurrentDocument() {
  if (pendingCloseTabId.value) closeTab(pendingCloseTabId.value)
  pendingCloseTabId.value = null
  showCloseDocumentConfirm.value = false
}

function requestCloseProject() {
  showCloseProjectConfirm.value = true
}

async function performCloseProject() {
  await closeProject()
  tabs.value = []
  activeTabId.value = null
  setDraftView('editor')
  showCloseProjectConfirm.value = false
}

// -- Event handlers ------------------------------------------------------

function navigateToLine(line: number) {
  setDraftView('editor')
  nextTick(() => {
    monacoEditor.value?.revealLineInCenter(line)
    monacoEditor.value?.setPosition({ lineNumber: line, column: 1 })
    monacoEditor.value?.focus()
  })
}

function toggleEditorMode() {
  setDraftView(isLatexMode.value ? 'editor' : 'latex')
}

function addSection() {
  insertTextAtCursor(
    `${content.value.endsWith('\n') ? '' : '\n'}\n## ${t('editor.newSection')}\n\n`,
  )
}

async function handleSelectionTask(action: string) {
  const target = selection.value.text || content.value
  if (!target.trim()) return
  // The global Agent dock is the only AI task surface in every editor mode.
  toggleAgentDock(true)
  // Capture read-only surrounding lines so the agent can keep transitions,
  // terminology and style coherent. The editable range stays the selection.
  let beforeContext: string | undefined
  let afterContext: string | undefined
  if (selection.value.text) {
    const lines = content.value.split('\n')
    // startLine/endLine are 1-based (Monaco convention).
    const beforeEnd = selection.value.startLine - 1 // exclusive end → last line before selection
    const before = lines.slice(Math.max(0, beforeEnd - 5), beforeEnd)
    const after = lines.slice(selection.value.endLine, selection.value.endLine + 5)
    beforeContext = before.join('\n') || undefined
    afterContext = after.join('\n') || undefined
  }
  await sendAgentMessage(
    t('editor.selectionTaskPrompt', {
      action,
      target: selection.value.text ? t('editor.selectedText') : t('editor.documentTarget'),
    }),
    target,
    '',
    rootDir.value || undefined,
    activeFile.value || undefined,
    [],
    selection.value.text && activeFile.value
      ? {
          selection: {
            filePath: activeFile.value,
            startLine: selection.value.startLine,
            startColumn: selection.value.startCol,
            endLine: selection.value.endLine,
            endColumn: selection.value.endCol,
            text: selection.value.text,
            beforeContext,
            afterContext,
          },
        }
      : undefined,
  )
}

async function openWorkspaceFolder() {
  try {
    const selected = await openDialog({ directory: true, multiple: false })
    if (selected) {
      window.dispatchEvent(new CustomEvent('open-workspace-folder', { detail: { path: selected } }))
      // Auto-detect and load project metadata if available
      const isProject = await useProject().detectProject(selected as string)
      if (isProject) {
        try {
          await useProject().openProject(selected as string)
        } catch {
          /* */
        }
      }
    }
  } catch {
    /* cancelled */
  }
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

async function handleProjectCreated(path: string) {
  showProjectStart.value = false
  try {
    await openProjectWorkspace(path, { draftView: 'editor' })
  } catch (e) {
    danger(e instanceof Error ? e.message : t('project.openFailed'))
  }
}

async function handleOpenRecentProject(path: string) {
  try {
    await openProjectWorkspace(path, { restoreView: true })
  } catch (e) {
    danger(e instanceof Error ? e.message : t('editor.openRecentFailed'))
  }
}

function enterEditorFromMindMap(outline: string) {
  saveMindMap()
  setDraftView('editor')
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

function buildTreeNode(
  parentId: string,
  node: import('../composables/useMindMap').MindMapTreeNode,
) {
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
  _contentBeforeMindMap = content.value
  if (hasSavedMindMap.value) {
    loadSavedMindMap()
    setDraftView('mindmap')
    return
  }
  if (await loadFromBackend()) {
    setDraftView('mindmap')
    return
  }
  skipNextBackendLoad()
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
  setDraftView('mindmap')
}

async function handleSaveFile() {
  const err = await saveFile()
  showExportToast(err || t('editor.saved'))
}

async function handleProcessCitations() {
  if (!content.value.trim()) {
    showExportToast(t('editor.pleaseInputContent'))
    return
  }
  try {
    const preview = await previewCitations(content.value)
    const data = await processCitations(content.value, [], 'ieee')
    if (!data?.text) {
      showExportToast(t('editor.citationFailed'))
      return
    }
    if (activeTab.value) {
      setContent(`${data.text}${data.bibliography || ''}`)
      markDirty()
    }
    showExportToast(
      t('editor.citationCount', { count: preview?.unique_count ?? data.citations?.length ?? 0 }),
    )
  } catch (e) {
    showExportToast(t('editor.citationFailedMsg', { msg: String(e) }))
  }
}

async function handleZoteroInsert() {
  zoteroPromptError.value = ''
  showZoteroPrompt.value = true
  // 预检连接模式：本地 Zotero 免 Key 时给出对应提示
  try {
    const status = await getZoteroStatus()
    zoteroMode.value = status?.mode ?? null
  } catch {
    zoteroMode.value = null
  }
}

async function submitZoteroSearch(query: string) {
  zoteroSearching.value = true
  zoteroPromptError.value = ''
  try {
    const status = await getZoteroStatus()
    if (status && status.connected === false) {
      zoteroPromptError.value = status.message || t('editor.zoteroConfig')
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
  } catch {
    showExportToast(t('editor.imageUploadFailed'))
  }
}

async function handleVisionSelected(file: File, mode: VisionAnalysisType = 'general') {
  try {
    let data: VisionAnalysisResponse | null
    if (mode === 'ocr') data = await ocrImage(file)
    else if (mode === 'chart') data = await analyzeChart(file)
    else if (mode === 'table') data = await extractTableFromImage(file)
    else if (mode === 'formula') data = await recognizeFormula(file)
    else data = await analyzeVision(file, 'general')
    if (!data) {
      showExportToast(t('editor.visionFailed'))
      return
    }
    // 本地 OCR 都不可用时，不把错误提示写进文档，只提示用户
    if (data.engine === 'none') {
      showExportToast(t('editor.visionLocalUnavailable'))
      return
    }
    const localOcrEngine =
      data.engine === 'tesseract' || data.engine === 'paddleocr' ? data.engine : null
    if (mode === 'ocr' || mode === 'formula') {
      // OCR 转写 / 公式识别结果按原文直接插入
      insertTextAtCursor(`\n\n${data.text || data.raw_description || t('editor.visionNoText')}\n`)
    } else {
      const findings = data.key_findings?.length
        ? `\n${t('editor.visionFindings', { findings: data.key_findings.join('; ') })}`
        : ''
      const chart = data.chart_type
        ? `\n${t('editor.visionChartType', { type: data.chart_type })}`
        : ''
      const table = data.table_data?.length
        ? `\n\n${data.table_data.map((row: string[]) => `| ${row.join(' | ')} |`).join('\n')}`
        : ''
      insertTextAtCursor(
        `\n\n> Vision：${data.text || data.raw_description || t('editor.visionNoText')}${chart}${findings}${table}\n`,
      )
    }
    showExportToast(
      localOcrEngine
        ? t('editor.visionInsertedLocal', { engine: localOcrEngine })
        : t('editor.visionInserted'),
    )
  } catch (e) {
    showExportToast(t('editor.visionFailedMsg', { msg: String(e) }))
  }
}

async function runComplianceCheck() {
  if (!content.value.trim()) {
    complianceError.value = t('editor.editorEmpty')
    showCompliance.value = true
    return
  }
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
  } catch (e) {
    complianceError.value = t('editor.requestFailed', { msg: String(e) })
  } finally {
    complianceLoading.value = false
  }
}

const companion = useArgumentCompanion()

// Wire argument companion: setDoc on tab switch, onEditorEdit on content change
watch(
  activeTab,
  (tab) => {
    if (tab?.docId) companion.setDoc(tab.docId, tab.name)
  },
  { immediate: true },
)

function onContentChange(value: string) {
  companion.onEditorEdit(value)
}
function onSelectionChange(_sel: unknown) {}

function insertTable() {
  const sr = 3,
    sc = 3
  const header = `| ${Array.from({ length: sc }, (_, i) => `Column ${i + 1}`).join(' | ')} |`
  const sep = `| ${Array.from({ length: sc }, () => '---').join(' | ')} |`
  const body = Array.from(
    { length: sr - 1 },
    () => `| ${Array.from({ length: sc }, () => '').join(' | ')} |`,
  )
  insertTextAtCursor(`\n${[header, sep, ...body].join('\n')}\n`)
}
function insertInlineFormula() {
  insertTextAtCursor('$ $')
}
function insertBlockFormula() {
  insertTextAtCursor('\n$$\n\n$$\n')
}
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
  const cursorMoved =
    pos &&
    (pos.lineNumber !== voiceRange.line ||
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
      ed.executeEdits('voice', [
        {
          range: new Range(
            voiceRange.line,
            voiceRange.col,
            voiceRange.line,
            voiceRange.col + voiceRange.len,
          ),
          text: newText,
        },
      ])
      voiceRange.len = newText.length
    }
    return
  }

  ed.executeEdits('voice', [
    {
      range: new Range(
        voiceRange.line,
        voiceRange.col,
        voiceRange.line,
        voiceRange.col + voiceRange.len,
      ),
      text,
    },
  ])
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
  exportToastTimer = setTimeout(() => {
    exportMessage.value = ''
  }, 3000)
}

// -- Keyboard -------------------------------------------------------------
function onKeyDown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 's') {
    e.preventDefault()
    handleSaveFile()
  }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'b') {
    e.preventDefault()
    sidebarCollapsed.value = !sidebarCollapsed.value
  }
}

// -- Lifecycle -------------------------------------------------------------
onMounted(() => {
  window.addEventListener('keydown', onKeyDown)
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
  if (draftView.value === 'mindmap') {
    void openMindMapFromEditor()
  }
})

onBeforeUnmount(() => {
  if (exportToastTimer) clearTimeout(exportToastTimer)
  window.removeEventListener('keydown', onKeyDown)
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
  if (format === 'word' || format === 'pdf' || format === 'latex') {
    exportWorkspace.format.value = format
    navigate('export')
  }
}

function handleVoiceAiPreset(e: Event) {
  const { action } = (e as CustomEvent).detail
  void handleSelectionTask(action)
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
  border: 1px solid var(--border-color);
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
  border-color: rgba(var(--c-accent-rgb), 0.2);
  box-shadow: 0 8px 24px rgba(var(--c-accent-rgb), 0.15);
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
.rp-content {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

/* -- Responsive --------------------------------------------- */
@media (max-width: 1180px) {
  .layout-sidebar {
    width: 220px !important;
  }
  .layout-sidebar.collapsed {
    width: 44px !important;
  }
  .layout-panel {
    max-width: 42vw;
  }
}
@media (max-width: 980px) {
  .layout-sidebar,
  .sidebar-resize {
    display: none;
  }
  .layout-panel {
    width: min(420px, 46vw) !important;
    min-width: 320px;
  }
}
@media (max-width: 820px) {
  .layout-panel-wrapper {
    display: none;
  }
}

/* Reference-driven workbench overrides */
.editor-layout {
  flex-direction: column;
  background: var(--c-app-bg);
}
.editor-layout > :deep(.mindmap-view),
.editor-layout > :deep(.editor-welcome) {
  flex: 1;
  min-height: 0;
}
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
  transition:
    color 0.15s ease,
    background 0.15s ease;
}
.sidebar-tab:hover {
  color: var(--c-text-1);
  background: var(--c-surface-2);
}
.sidebar-tab.active {
  color: var(--c-accent);
  background: var(--c-accent-soft);
}
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
.editor-surface > :deep(.central-outline) {
  height: 100%;
}
.document-preview {
  max-width: none;
  padding: 42px clamp(28px, 5vw, 80px);
  overflow: auto;
}
.central-outline {
  max-width: 760px;
  margin: 24px auto;
  border: 1px solid var(--c-border);
  border-radius: 10px;
  overflow: hidden;
}
.header-chapter {
  color: var(--c-text-2);
  font-size: 12px;
}
.header-action,
.header-icon {
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
  font:
    500 12px/1 var(--font-sans),
    var(--font-zh);
  cursor: pointer;
}
.header-icon {
  width: 36px;
  padding: 0;
}
.header-action:hover,
.header-icon:hover {
  background: var(--c-surface-2);
  color: var(--c-text-0);
}
.header-action.primary {
  border-color: var(--c-accent);
  background: var(--c-accent);
  color: #fff;
}
.header-action:focus-visible,
.header-icon:focus-visible {
  outline: none;
  box-shadow: var(--ring-focus);
}
.writing-mode :deep(.editor-toolbar),
.latex-mode :deep(.editor-toolbar) {
  flex: 0 0 auto;
  border-color: var(--c-border);
  background: var(--c-panel);
  box-shadow: none;
}
.writing-mode :deep(.editor-tabs) {
  display: none;
}
.latex-mode :deep(.editor-tabs) {
  border-color: var(--c-border);
  background: var(--c-panel);
}

@media (max-width: 1180px) {
  .workbench-left {
    width: 208px !important;
  }
  .workbench-right {
    width: 332px !important;
    min-width: 300px;
  }
}
@media (max-width: 980px) {
  .workbench-left {
    width: 190px !important;
  }
  .header-action:not(.primary) {
    display: none;
  }
  .editor-workbench {
    position: relative;
  }
  .workbench-right {
    position: absolute;
    z-index: 35;
    top: 0;
    right: 0;
    bottom: 0;
    width: min(356px, calc(100% - 56px)) !important;
    box-shadow: var(--elevation-3);
  }
}
@media (max-width: 760px) {
  .workbench-left {
    display: none;
  }
  .header-action,
  .header-icon {
    height: 32px;
  }
  .header-icon {
    width: 32px;
  }
}
</style>
