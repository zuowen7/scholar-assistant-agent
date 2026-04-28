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

        <!-- Welcome screen -->
        <div v-if="!activeTab" class="editor-welcome">
          <div class="welcome-content">
            <div class="welcome-hero">
              <GraduationCap :size="36" class="hero-icon" />
              <div class="hero-text">
                <p class="hero-kicker">Scholar Workspace</p>
                <h1 class="hero-title">开始写作</h1>
              </div>
            </div>

            <p class="welcome-section-label">快速开始</p>
            <div class="welcome-cards">
              <button class="wc-card" @click="showProjectStart = true">
                <span class="wc-icon"><Workflow :size="18" /></span>
                <div class="wc-text">
                  <strong>新建工程</strong>
                  <span>思维导图 → 论文草稿</span>
                </div>
              </button>
              <button class="wc-card" @click="showTemplatePicker = true">
                <span class="wc-icon accent"><FileText :size="18" /></span>
                <div class="wc-text">
                  <strong>从模板新建</strong>
                  <span>IEEE / ACM / 自定义</span>
                </div>
              </button>
              <button class="wc-card" @click="openWorkspaceFolder">
                <span class="wc-icon"><FolderOpen :size="18" /></span>
                <div class="wc-text">
                  <strong>打开文件夹</strong>
                  <span>继续现有工程</span>
                </div>
              </button>
              <button class="wc-card" @click="openNewUntitled">
                <span class="wc-icon"><FilePlus :size="18" /></span>
                <div class="wc-text">
                  <strong>空白文档</strong>
                  <span>直接进入编辑器</span>
                </div>
              </button>
            </div>

            <div class="welcome-shortcuts">
              <kbd>Ctrl+K</kbd> AI 编辑 &nbsp;·&nbsp; <kbd>Ctrl+S</kbd> 保存 &nbsp;·&nbsp; <kbd>Tab</kbd> 接受补全
            </div>
          </div>
        </div>

        <template v-else>
          <!-- Slim toolbar -->
          <div class="editor-toolbar" @click.stop>
            <!-- Hidden file inputs -->
            <input
              ref="imageInputRef"
              class="hidden-file-input"
              type="file"
              accept="image/png,image/jpeg,image/gif,image/webp,image/bmp"
              @change="handleImageSelected"
            />
            <input
              ref="visionInputRef"
              class="hidden-file-input"
              type="file"
              accept="image/png,image/jpeg,image/gif,image/webp,image/bmp"
              @change="handleVisionSelected"
            />

            <div class="tb-left">
              <button class="tb-btn" title="新建论文" @click="showTemplatePicker = true" aria-label="新建论文">
                <FilePlus :size="15" :stroke-width="1.7" />
              </button>
              <button class="tb-btn" title="保存 (Ctrl+S)" @click="handleSaveFile" aria-label="保存">
                <Save :size="15" :stroke-width="1.7" />
              </button>
              <div class="tb-divider" />
              <kbd class="tb-kbd">Ctrl+K · AI</kbd>
            </div>

            <div class="tb-right">
              <div v-if="exportMessage" class="export-toast">{{ exportMessage }}</div>

              <button
                class="tb-btn"
                title="思维导图"
                aria-label="思维导图"
                @click="openMindMapFromEditor"
              >
                <Workflow :size="15" :stroke-width="1.7" />
              </button>
              <button
                class="tb-btn"
                :class="{ active: rightPanelTab === 'preview' }"
                title="预览"
                aria-label="预览"
                @click="toggleRightPanel('preview')"
              >
                <Eye :size="15" :stroke-width="1.7" />
              </button>
              <button
                class="tb-btn"
                :class="{ active: rightPanelTab === 'ai' }"
                title="AI 编辑"
                aria-label="AI 编辑面板"
                @click="toggleRightPanel('ai')"
              >
                <Bot :size="15" :stroke-width="1.7" />
              </button>
              <button
                class="tb-btn"
                :class="{ active: rightPanelTab === 'argument' }"
                title="论证导图"
                aria-label="论证导图"
                @click="toggleRightPanel('argument')"
              >
                <GitBranch :size="15" :stroke-width="1.7" />
              </button>
              <div class="tb-divider" />

              <!-- More actions dropdown -->
              <UiDropdown :items="toolbarMoreItems" :width="230" align="end">
                <template #trigger>
                  <button class="tb-btn" title="更多工具" aria-label="更多工具">
                    <MoreHorizontal :size="15" :stroke-width="1.7" />
                  </button>
                </template>
                <template v-if="exportTemplates.length" #default>
                  <div class="dd-template-row">
                    <span class="dd-template-label">LaTeX 模板</span>
                    <select
                      class="dd-template-select"
                      v-model="selectedTemplate"
                      :disabled="exportLoading"
                    >
                      <option v-for="t in exportTemplates" :key="t.id" :value="t.id">{{ t.name }}</option>
                    </select>
                  </div>
                </template>
              </UiDropdown>
            </div>
          </div>

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
          <button
            class="rp-tab"
            :class="{ active: rightPanelTab === 'preview' }"
            @click="rightPanelTab = 'preview'"
          >
            <Eye :size="13" :stroke-width="1.7" />
            预览
          </button>
          <button
            class="rp-tab"
            :class="{ active: rightPanelTab === 'ai' }"
            @click="rightPanelTab = 'ai'"
          >
            <Bot :size="13" :stroke-width="1.7" />
            AI 编辑
          </button>
          <button
            class="rp-tab"
            :class="{ active: rightPanelTab === 'argument' }"
            @click="rightPanelTab = 'argument'"
          >
            <GitBranch :size="13" :stroke-width="1.7" />
            论证
          </button>
          <button
            class="rp-close"
            title="关闭面板"
            aria-label="关闭面板"
            @click="rightPanelTab = null"
          >
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
        <ArgumentMap
          v-if="rightPanelTab === 'argument'"
          class="rp-content"
        />
      </div>
    </template>

    <!-- Modals -->
    <ComplianceModal
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

    <div v-if="showProjectStart" class="project-start-backdrop" @click.self="showProjectStart = false">
      <div class="project-start-dialog">
        <div class="project-start-header">
          <div>
            <div class="welcome-kicker">New Project</div>
            <h3>新建工程</h3>
          </div>
          <button class="project-start-close" @click="showProjectStart = false" aria-label="关闭">
            <X :size="18" :stroke-width="2" />
          </button>
        </div>
        <div class="project-start-options">
          <button class="project-start-option primary" @click="startProjectInEditor">
            <strong>直接进入编辑器</strong>
            <span>创建空白文档，保持现有写作流程。</span>
          </button>
          <div class="project-start-option">
            <strong>先创建思维导图</strong>
            <span>先梳理论文结构，再保存并进入编辑器。</span>
            <div class="project-topic-row">
              <input
                v-model="projectTopic"
                class="project-topic-input"
                placeholder="输入研究主题（可选）"
                @keydown.enter="startProjectWithMindMap"
              />
              <button class="project-topic-go" @click="startProjectWithMindMap">创建</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import MonacoEditor from './MonacoEditor.vue'
import MarkdownPreview from './MarkdownPreview.vue'
import FileTree from './FileTree.vue'
import EditorTabs from './EditorTabs.vue'
import AiPanel from './AiPanel.vue'
import ArgumentMap from './ArgumentMap.vue'
import ComplianceModal from './ComplianceModal.vue'
import TemplatePicker from './TemplatePicker.vue'
import MindMapView from './MindMapView.vue'
import UiDropdown from './ui/UiDropdown.vue'
import type { DropdownItem } from './ui/UiDropdown.vue'
import {
  FilePlus, Save, Eye, Bot, GitBranch, Workflow, MoreHorizontal,
  Image, Table, Sigma, Quote, Library, Code2, CheckCircle, Download,
  GraduationCap, FileText, FolderOpen, X, ChevronLeft, ChevronRight,
} from './ui/icons'
import { useEditor } from '../composables/useEditor'
import { useMindMap, mindMapToMarkdown, markdownToMindMapNodes } from '../composables/useMindMap'
import { API_BASE } from '../utils/api'
import { readSseStream } from '../utils/streamReader'

async function saveBlob(blob: Blob, defaultName: string): Promise<string | null> {
  // Try Tauri: use save dialog, then write via @tauri-apps/plugin-fs
  try {
    const { save } = await import('@tauri-apps/plugin-dialog')
    const { writeFile } = await import('@tauri-apps/plugin-fs')
    const ext = defaultName.split('.').pop() || 'bin'
    const path = await save({
      defaultPath: defaultName,
      filters: [{ name: ext.toUpperCase(), extensions: [ext] }],
    })
    if (!path) return 'Cancelled'
    const buffer = new Uint8Array(await blob.arrayBuffer())
    await writeFile(path, buffer)
    // Open with system default app
    const { open } = await import('@tauri-apps/plugin-shell')
    open(path)
    return null
  } catch (e) {
    console.warn('Tauri save failed:', e)
  }
  // Browser fallback
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = defaultName
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  setTimeout(() => URL.revokeObjectURL(url), 1000)
  return null
}

const props = defineProps<{ isDark: boolean }>()
const workspaceMode = ref<'editor' | 'mindmap'>('editor')
const showProjectStart = ref(false)
const { resetMindMap, loadSavedMindMap, saveMindMap, addChild, updateNodeText } = useMindMap()

// ── Right panel: unified tab ─────────────────────────────────────────────────
type RightTab = 'preview' | 'ai' | 'argument'
const rightPanelTab = ref<RightTab | null>(null)

function toggleRightPanel(tab: RightTab) {
  if (rightPanelTab.value === tab) {
    rightPanelTab.value = null
  } else {
    rightPanelTab.value = tab
  }
}

const {
  content, contentVersion, activeTab, selection,
  aiLoading, aiResult,
  previousContent,
  openNewUntitled, setContent, markDirty,
  saveFile, exportToWord, insertTextAtCursor, insertImageFile, analyzeVision,
  insertTable, insertInlineFormula, insertBlockFormula, processCitations,
  previewCitations, getZoteroStatus, searchZotero, insertZoteroCitation,
  aiEdit, applyAiResult, undoEdit, tabs,
  onDidChangeContent, acceptGhostText, clearGhostText,
} = useEditor()

// ── Template picker ───────────────────────────────────────────────────────────
const showTemplatePicker = ref(false)
const workspaceFiles = computed(() =>
  tabs.value.map(t => ({ name: t.name || t.path?.split(/[\\/]/).pop() || 'untitled', content: t.content }))
)
const imageInputRef = ref<HTMLInputElement | null>(null)
const visionInputRef = ref<HTMLInputElement | null>(null)
const assetLoading = ref(false)

function startProjectInEditor() {
  showProjectStart.value = false
  workspaceMode.value = 'editor'
  openNewUntitled()
}

const projectTopic = ref('')

function startProjectWithMindMap() {
  showProjectStart.value = false
  sidebarCollapsed.value = true
  resetMindMap(projectTopic.value.trim() || undefined)
  projectTopic.value = ''
  workspaceMode.value = 'mindmap'
}

function enterEditorFromMindMap(outline: string) {
  saveMindMap()
  workspaceMode.value = 'editor'
  if (!activeTab.value) openNewUntitled()
  nextTick(() => {
    if (activeTab.value && outline.trim()) {
      setContent(outline)
    }
  })
}

function openMindMapFromEditor() {
  sidebarCollapsed.value = true
  const md = content.value
  if (md.trim()) {
    const tree = markdownToMindMapNodes(md)
    if (tree) {
      resetMindMap(tree.text)
      const rootId = useMindMap().draftMindMap.value.rootId
      for (const child of tree.children) {
        addChild(rootId)
        const newNodeId = useMindMap().selectedNodeId.value
        updateNodeText(newNodeId, child.text)
        for (const grandChild of child.children) {
          addChild(newNodeId)
          const gcId = useMindMap().selectedNodeId.value
          updateNodeText(gcId, grandChild.text)
        }
      }
      useMindMap().selectNode(rootId)
    } else {
      loadSavedMindMap()
    }
  } else {
    loadSavedMindMap()
  }
  workspaceMode.value = 'mindmap'
}

// ── Toolbar more-actions dropdown ─────────────────────────────────────────────
const toolbarMoreItems = computed<DropdownItem[]>(() => [
  { label: '插入' },
  { text: '图片', icon: Image, onClick: openImagePicker, disabled: assetLoading.value },
  { text: '表格 3×3', icon: Table, onClick: handleInsertTable },
  { text: '行内公式', icon: Sigma, onClick: handleInsertInlineFormula },
  { text: '块级公式', icon: Sigma, onClick: handleInsertBlockFormula },
  { divider: true },
  { label: '分析' },
  { text: 'OCR / Vision', icon: Eye, onClick: openVisionPicker, disabled: assetLoading.value },
  { text: '论文合规检查', icon: CheckCircle, onClick: runComplianceCheck },
  { divider: true },
  { label: '引用' },
  { text: '编号引用', icon: Quote, onClick: handleProcessCitations, disabled: assetLoading.value },
  { text: 'Zotero 搜索', icon: Library, onClick: handleZoteroInsert, disabled: assetLoading.value },
  { divider: true },
  { label: '导出' },
  { text: 'Word (.docx)', icon: Download, onClick: handleExportWord, disabled: exportLoading.value },
  { text: 'LaTeX (.tex)', icon: Code2, onClick: handleExportLatex, disabled: !selectedTemplate.value || exportLoading.value },
  {
    text: 'PDF',
    icon: Download,
    onClick: handleExportPdf,
    disabled: !selectedTemplate.value || exportLoading.value || !tectonicAvailable.value,
  },
])

async function openWorkspaceFolder() {
  try {
    const { open } = await import('@tauri-apps/plugin-dialog')
    const selected = await open({ directory: true, multiple: false })
    if (selected) {
      window.dispatchEvent(new CustomEvent('open-workspace-folder', { detail: { path: selected } }))
    }
  } catch {
    // dialog cancelled
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

function openImagePicker() { imageInputRef.value?.click() }
function openVisionPicker() { visionInputRef.value?.click() }

async function handleImageSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || assetLoading.value) return
  assetLoading.value = true
  try {
    const data = await insertImageFile(file)
    showExportToast(data ? 'Image inserted' : 'Image upload failed')
  } catch (e) {
    showExportToast(`Image upload failed: ${e}`)
  } finally {
    assetLoading.value = false
  }
}

async function handleVisionSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || assetLoading.value) return
  assetLoading.value = true
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
  } catch (e) {
    showExportToast(`Vision analysis failed: ${e}`)
  } finally {
    assetLoading.value = false
  }
}

function handleInsertTable() { insertTable(3, 3) }
function handleInsertInlineFormula() { insertInlineFormula() }
function handleInsertBlockFormula() { insertBlockFormula() }

async function handleProcessCitations() {
  if (!content.value.trim()) { showExportToast('Please write content in the editor first'); return }
  assetLoading.value = true
  try {
    const preview = await previewCitations(content.value)
    const data = await processCitations(content.value, [], 'ieee')
    if (!data?.text) { showExportToast('Citation indexing failed'); return }
    if (activeTab.value) { setContent(`${data.text}${data.bibliography || ''}`); markDirty() }
    showExportToast(`Indexed ${preview?.unique_count ?? data.citations?.length ?? 0} citations`)
  } catch (e) {
    showExportToast(`Citation indexing failed: ${e}`)
  } finally {
    assetLoading.value = false
  }
}

async function handleZoteroInsert() {
  const query = window.prompt('Search Zotero')
  if (!query?.trim() || assetLoading.value) return
  assetLoading.value = true
  try {
    const status = await getZoteroStatus()
    if (status && status.connected === false) { showExportToast('Please configure Zotero API first'); return }
    const items = await searchZotero(query.trim(), 5)
    const item = items[0]
    if (!item?.key) { showExportToast('No Zotero result found'); return }
    await insertZoteroCitation(item.key)
    showExportToast(`Inserted ${item.citation_key || item.key}`)
  } catch (e) {
    showExportToast(`Zotero search failed: ${e}`)
  } finally {
    assetLoading.value = false
  }
}

// ── Compliance ────────────────────────────────────────────────────────────────
const showCompliance = ref(false)
const complianceLoading = ref(false)
const complianceError = ref('')
const complianceReport = ref<Record<string, unknown> | null>(null)

async function runComplianceCheck() {
  if (!content.value.trim()) {
    complianceError.value = 'Editor content is empty'
    showCompliance.value = true
    return
  }
  complianceLoading.value = true
  complianceError.value = ''
  complianceReport.value = null
  showCompliance.value = true
  try {
    const resp = await fetch(`${EXPORT_API}/api/compliance`, {
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
  } catch (e) {
    complianceError.value = `请求失败: ${e}`
  } finally {
    complianceLoading.value = false
  }
}

// ── Layout / resize ───────────────────────────────────────────────────────────
const sidebarWidth = ref(296)
const collapsedSidebarWidth = 44
const sidebarCollapsed = ref(false)
const panelWidth = ref(300)

function onContentChange(_value: string) {}
function onSelectionChange(_sel: unknown) {}

function handleAiEdit(instruction: string, taskType?: string) {
  const contextText = selection.value.text || content.value
  aiEdit(instruction, contextText || '', taskType)
}

async function handleAgentRequest(instruction: string) {
  const contextText = selection.value.text || content.value
  try {
    const resp = await fetch(`${EXPORT_API}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: instruction, context_text: contextText || undefined }),
    })
    if (resp.ok) {
      const reader = resp.body?.getReader()
      if (!reader) return
      await readSseStream(reader, (_type, evt) => {
        if (evt.content) aiResult.value = (aiResult.value || '') + (evt.content as string)
      })
    }
  } catch (e) { console.warn('handleAgentRequest failed:', e) }
}

async function handleExportWord() {
  if (exportLoading.value) return
  exportLoading.value = true
  try {
    const err = await exportToWord()
    showExportToast(err || 'Word download started')
  } catch (e) {
    showExportToast(`Word export failed: ${e}`)
  } finally {
    exportLoading.value = false
  }
}

async function handleStyleTransfer(templateId: string, templateName: string) {
  const contextText = selection.value.text || content.value
  if (!contextText.trim()) return
  try {
    await fetch(`${EXPORT_API}/api/paper-style-transfer`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: contextText, template_id: templateId, section: 'introduction' }),
    })
    aiEdit(`Rewrite in ${templateName} style`, contextText, 'expand')
  } catch (e) { console.warn('handleStyleTransfer failed:', e) }
}

function handleInsert(text: string) { aiResult.value = text; applyAiResult() }
function handleUndo() { undoEdit() }

async function handleSaveFile() {
  const err = await saveFile()
  if (err) showExportToast(err)
  else showExportToast('Saved')
}

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
    _activeResizeMove = null
    _activeResizeUp = null
  }
  _activeResizeMove = onMouseMove
  _activeResizeUp = onMouseUp
  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', onMouseUp)
}

async function onKeyDown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 's') {
    e.preventDefault()
    try {
      const err = await saveFile()
      if (err) showExportToast(err)
    } catch (err) { showExportToast(String(err)) }
  }
  if (e.key === 'Tab' && !e.ctrlKey && !e.metaKey && !e.shiftKey && acceptGhostText()) {
    e.preventDefault()
  }
  if (e.key === 'Escape') clearGhostText()
}

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

onMounted(() => {
  window.addEventListener('keydown', onKeyDown)
  loadExportTemplates()
  window.addEventListener('paper-scaffold', handlePaperScaffold)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeyDown)
  window.removeEventListener('paper-scaffold', handlePaperScaffold)
  if (_activeResizeMove) document.removeEventListener('mousemove', _activeResizeMove)
  if (_activeResizeUp) document.removeEventListener('mouseup', _activeResizeUp)
})

// ── Export ────────────────────────────────────────────────────────────────────
const EXPORT_API = API_BASE
const exportTemplates = ref<{ id: string; name: string; description: string }[]>([])
const selectedTemplate = ref('')
const exportLoading = ref(false)
const exportMessage = ref('')
let exportToastTimer: ReturnType<typeof setTimeout> | null = null

const tectonicAvailable = ref(false)

async function loadExportTemplates() {
  try {
    const resp = await fetch(`${EXPORT_API}/api/export/templates`)
    if (resp.ok) {
      const data = await resp.json()
      exportTemplates.value = data.templates || []
      tectonicAvailable.value = data.tectonic_available || false
      if (exportTemplates.value.length && !selectedTemplate.value) {
        selectedTemplate.value = exportTemplates.value[0].id
      }
    }
  } catch (e) { console.warn('loadExportTemplates failed:', e) }
}

async function handleExportLatex() {
  if (!selectedTemplate.value || exportLoading.value) return
  if (!content.value.trim()) { showExportToast('Please write content in the editor first'); return }
  exportLoading.value = true
  try {
    const resp = await fetch(`${EXPORT_API}/api/export`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ markdown: content.value, template_id: selectedTemplate.value }),
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ error: '导出失败' }))
      showExportToast(err.error || '导出失败')
      return
    }
    const data = await resp.json()
    const tex = data.tex || ''
    if (!tex) { showExportToast('转换结果为空'); return }
    await navigator.clipboard.writeText(tex)
    showExportToast('LaTeX copied to clipboard')
  } catch (e) {
    showExportToast(`导出失败: ${e}`)
  } finally {
    exportLoading.value = false
  }
}

async function handleExportPdf() {
  if (!selectedTemplate.value || exportLoading.value) return
  if (!content.value.trim()) { showExportToast('Please write content in the editor first'); return }
  if (!tectonicAvailable.value) { showExportToast('Please install the LaTeX engine (Tectonic) first'); return }
  exportLoading.value = true
  try {
    const resp = await fetch(`${EXPORT_API}/api/export/pdf`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        markdown: content.value,
        template_id: selectedTemplate.value,
        title: activeTab.value?.name?.replace(/\.md$/i, '') || 'paper',
      }),
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: 'PDF 导出失败' }))
      showExportToast(err.detail || err.error || 'PDF 导出失败')
      return
    }
    const blob = await resp.blob()
    const filename = 'paper.pdf'
    const saveErr = await saveBlob(blob, filename)
    if (saveErr === 'Cancelled') { showExportToast('已取消'); return }
    if (saveErr) { showExportToast(`保存失败: ${saveErr}`); return }
    showExportToast('PDF saved')
  } catch (e) {
    showExportToast(`PDF 导出失败: ${e}`)
  } finally {
    exportLoading.value = false
  }
}

function showExportToast(msg: string) {
  if (exportToastTimer) clearTimeout(exportToastTimer)
  exportMessage.value = msg
  exportToastTimer = setTimeout(() => { exportMessage.value = '' }, 3000)
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

/* ── Welcome ──────────────────────────────────────────────── */
.editor-welcome {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-7) var(--space-6);
  background: var(--editor-bg);
  overflow-y: auto;
}

.welcome-content { width: min(480px, 100%); }

.welcome-hero {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  margin-bottom: var(--space-6);
}

.hero-icon { color: var(--c-accent); flex-shrink: 0; }

.hero-kicker {
  margin: 0 0 2px;
  color: var(--c-accent);
  font-size: var(--text-xs);
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.hero-title {
  margin: 0;
  font-size: var(--text-3xl);
  font-weight: 700;
  color: var(--c-text-0);
  line-height: var(--leading-tight);
}

.welcome-section-label {
  font-size: var(--text-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--c-text-3);
  margin-bottom: var(--space-2);
}

.welcome-cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-2);
  margin-bottom: var(--space-5);
}

.wc-card {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-3);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--toolbar-bg);
  color: var(--c-text-1);
  cursor: pointer;
  font: inherit;
  text-align: left;
  transition: border-color var(--motion-fast), background var(--motion-fast);
}
.wc-card:hover { border-color: var(--c-accent); background: var(--hover-bg); }

.wc-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  background: var(--c-surface-3);
  color: var(--c-text-2);
  flex-shrink: 0;
}
.wc-icon.accent { background: var(--c-accent-soft); color: var(--c-accent); }
.wc-card:hover .wc-icon { background: var(--c-accent-soft); color: var(--c-accent); }

.wc-text { display: flex; flex-direction: column; gap: 2px; }
.wc-text strong { font-size: var(--text-md); font-weight: 600; }
.wc-text span { font-size: var(--text-sm); color: var(--c-text-3); }

.welcome-shortcuts {
  font-size: var(--text-sm);
  color: var(--c-text-3);
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}
.welcome-shortcuts kbd {
  display: inline-flex;
  align-items: center;
  height: 20px;
  padding: 0 6px;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  background: var(--c-surface-4);
  color: var(--c-text-2);
  font: inherit;
  font-size: 11px;
}

/* ── Slim toolbar ─────────────────────────────────────────── */
.editor-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
  padding: 4px 8px;
  border-bottom: 1px solid var(--border-color);
  background: var(--toolbar-bg);
  min-height: 40px;
  flex-shrink: 0;
}

.tb-left, .tb-right {
  display: flex;
  align-items: center;
  gap: 2px;
}

.tb-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 28px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--c-text-3);
  cursor: pointer;
  transition: background var(--motion-fast) var(--ease-out),
              color var(--motion-fast) var(--ease-out);
  flex-shrink: 0;
}
.tb-btn:hover { background: var(--hover-bg); color: var(--c-text-0); }
.tb-btn.active { background: var(--c-accent-soft); color: var(--c-accent); }
.tb-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.tb-divider {
  width: 1px;
  height: 16px;
  background: var(--border-color);
  margin: 0 4px;
  flex-shrink: 0;
}

.tb-kbd {
  display: inline-flex;
  align-items: center;
  height: 20px;
  padding: 0 6px;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  background: var(--c-surface-4);
  color: var(--c-text-3);
  font: inherit;
  font-size: 11px;
  white-space: nowrap;
  cursor: default;
  flex-shrink: 0;
}

.export-toast {
  font-size: 11px;
  color: var(--c-success);
  padding: 3px 8px;
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--c-success) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--c-success) 25%, transparent);
  white-space: nowrap;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.hidden-file-input { display: none; }

/* ── More-dropdown extras ─────────────────────────────────── */
.dd-template-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px 8px;
  border-top: 1px solid var(--c-surface-3);
  margin-top: 4px;
}
.dd-template-label {
  font-size: var(--text-xs);
  color: var(--c-text-3);
  white-space: nowrap;
  flex-shrink: 0;
}
.dd-template-select {
  flex: 1;
  min-width: 0;
  background: var(--c-surface-2);
  border: 1px solid var(--c-surface-3);
  border-radius: var(--radius-sm);
  color: var(--c-text-1);
  font-size: var(--text-sm);
  padding: 4px 6px;
  cursor: pointer;
  outline: none;
}
.dd-template-select:hover { border-color: var(--c-accent); }
.dd-template-select:disabled { opacity: 0.5; cursor: not-allowed; }
.dd-template-select option { background: var(--c-surface-2); }

/* ── Right panel (unified tabs) ────────────────────────────── */
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
  gap: 0;
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
  transition: background var(--motion-fast), color var(--motion-fast);
}
.rp-close:hover { background: var(--hover-bg); color: var(--c-danger); }

.rp-content {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

/* ── Resize handle ────────────────────────────────────────── */
.resize-handle {
  width: 4px;
  cursor: col-resize;
  background: transparent;
  transition: background 0.15s;
  flex-shrink: 0;
}
.resize-handle:hover { background: var(--c-accent); }

/* ── New Project dialog ───────────────────────────────────── */
.project-start-backdrop {
  position: fixed;
  inset: 0;
  z-index: 80;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--c-overlay);
  backdrop-filter: blur(4px);
}
.project-start-dialog {
  width: min(520px, calc(100vw - 48px));
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  background: var(--panel-bg);
  color: var(--text-primary);
  box-shadow: var(--elevation-4);
}
.project-start-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  padding: 18px 20px;
  border-bottom: 1px solid var(--border-color);
}
.project-start-header h3 { margin: 4px 0 0; font-size: 20px; }
.welcome-kicker {
  color: var(--c-accent);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.project-start-close {
  border: 0;
  background: transparent;
  color: var(--c-text-3);
  cursor: pointer;
  display: flex;
  align-items: center;
  padding: 4px;
  border-radius: 4px;
}
.project-start-close:hover { color: var(--c-text-0); background: var(--hover-bg); }
.project-start-options { display: grid; gap: 10px; padding: 18px 20px 20px; }
.project-start-option {
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--toolbar-bg);
  color: var(--text-primary);
  text-align: left;
  padding: 14px 16px;
  cursor: pointer;
  font: inherit;
}
.project-start-option:hover { border-color: var(--c-accent); background: var(--hover-bg); }
.project-start-option.primary {
  background: color-mix(in srgb, var(--c-accent) 18%, var(--toolbar-bg));
  border-color: color-mix(in srgb, var(--c-accent) 55%, var(--border-color));
}
.project-start-option strong { display: block; margin-bottom: 5px; font-size: 14px; }
.project-start-option span { color: var(--c-text-3); font-size: 12px; line-height: 1.5; }
.project-topic-row { display: flex; gap: 8px; margin-top: 10px; }
.project-topic-input {
  flex: 1;
  height: 32px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--editor-bg);
  color: var(--text-primary);
  padding: 0 10px;
  font: inherit;
  font-size: 13px;
  outline: none;
}
.project-topic-input:focus { border-color: var(--c-accent); }
.project-topic-go {
  height: 32px;
  border: 1px solid var(--c-accent);
  border-radius: var(--radius-sm);
  background: var(--c-accent);
  color: #fff;
  padding: 0 16px;
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.project-topic-go:hover { opacity: 0.88; }

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
@media (max-width: 760px) {
  .editor-welcome { padding: 24px; }
  .welcome-cards { grid-template-columns: 1fr; }
  .editor-toolbar { gap: 4px; padding-inline: 6px; }
  .tb-kbd { display: none; }
}
@container (max-width: 520px) {
  .tb-kbd { display: none; }
}
</style>
