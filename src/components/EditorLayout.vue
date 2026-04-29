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

// 鈹€鈹€ Layout sub-components 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
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

// 鈹€鈹€ Icons 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
import { Eye, Bot, GitBranch, X } from './ui/icons'

// 鈹€鈹€ State composables 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
import { useEditorState } from '../composables/useEditorState'
import { useEditor } from '../composables/useEditor'
import { useEditorVision } from '../composables/useEditorVision'
import { useEditorCitation } from '../composables/useEditorCitation'
import { useEditorIO } from '../composables/useEditorIO'
import { useMindMap, mindMapToMarkdown, markdownToMindMapNodes } from '../composables/useMindMap'

const props = defineProps<{ isDark: boolean }>()

// 鈹€鈹€ Shared singleton state (single source of truth) 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
const { activeTab, content, contentVersion, selection, previousContent, tabs, aiResult, insertTextAtCursor } = useEditorState()

// 鈹€鈹€ Tab / file operations 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
const {
  openNewUntitled, setContent, markDirty,
  saveFile,
  onDidChangeContent, acceptGhostText, clearGhostText,
} = useEditor()

// 鈹€鈹€ AI edit actions (from useEditor, called once) 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
const { aiEdit, applyAiResult, undoEdit } = useEditor()

// 鈹€鈹€ Feature composables 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
const { analyzeVision, uploadImage, insertImageFile } = useEditorVision()
const { processCitations, previewCitations, getZoteroStatus, searchZotero } = useEditorCitation()
const { exportToWord, exportLatex, exportPdf, loadExportTemplates } = useEditorIO()
const { resetMindMap, loadSavedMindMap, saveMindMap, addChild, updateNodeText } = useMindMap()

// 鈹€鈹€ Workspace mode 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
const workspaceMode = ref<'editor' | 'mindmap'>('editor')
const sidebarCollapsed = ref(false)
const collapsedSidebarWidth = 44

// 鈹€鈹€ Right panel 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
type RightTab = 'preview' | 'ai' | 'argument'
const rightPanelTab = ref<RightTab | null>(null)
const toggleRightPanel = (tab: RightTab) => { rightPanelTab.value = rightPanelTab.value === tab ? null : tab }

// 鈹€鈹€ Export state 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
const exportTemplates = ref<{ id: string; name: string }[]>([])
const selectedTemplate = ref('')
const exportLoading = ref(false)
const exportMessage = ref('')
let exportToastTimer: ReturnType<typeof setTimeout> | null = null
const tectonicAvailable = ref(false)

// 鈹€鈹€ Compliance 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
const showCompliance = ref(false)
const complianceLoading = ref(false)
const complianceError = ref('')
const complianceReport = ref<Record<string, unknown> | null>(null)

// 鈹€鈹€ Template picker / project start 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
const showTemplatePicker = ref(false)
const showProjectStart = ref(false)

const workspaceFiles = computed(() =>
  tabs.value.map(t => ({ name: t.name || t.path?.split(/[\\/]/).pop() || 'untitled', content: t.content }))
)

// 鈹€鈹€ Event handlers 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

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
  showExportToast(err || '已保存')
}

async function handleExportWord() {
  if (exportLoading.value) return
  exportLoading.value = true
  try {
    const title = (activeTab.value?.name || 'Scholar Assistant Export').replace(/\.md$/i, '')
    const err = await exportToWord(content.value, title)
    showExportToast(err || 'Word 导出已开始')
  } catch (e) { showExportToast(`Word 导出失败：${e}`)
  } finally { exportLoading.value = false }
}

async function handleExportLatex() {
  if (!selectedTemplate.value || exportLoading.value) return
  if (!content.value.trim()) { showExportToast('请先输入内容'); return }
  exportLoading.value = true
  try {
    const { tex, error } = await exportLatex(content.value, selectedTemplate.value)
    if (error) { showExportToast(error); return }
    if (tex) { await navigator.clipboard.writeText(tex); showExportToast('LaTeX 已复制到剪贴板') }
    else showExportToast('转换结果为空')
  } catch (e) { showExportToast(`导出失败：${e}`)
  } finally { exportLoading.value = false }
}

async function handleExportPdf() {
  if (!selectedTemplate.value || exportLoading.value) return
  if (!content.value.trim()) { showExportToast('请先输入内容'); return }
  if (!tectonicAvailable.value) { showExportToast('请先安装 Tectonic'); return }
  exportLoading.value = true
  try {
    const title = (activeTab.value?.name || 'paper').replace(/\.md$/i, '')
    const err = await exportPdf(content.value, selectedTemplate.value, title)
    if (err === 'Cancelled') { showExportToast('已取消'); return }
    showExportToast(err || 'PDF 已保存')
  } catch (e) { showExportToast(`PDF 导出失败：${e}`)
  } finally { exportLoading.value = false }
}

async function handleProcessCitations() {
  if (!content.value.trim()) { showExportToast('请先输入内容'); return }
  try {
    const preview = await previewCitations(content.value)
    const data = await processCitations(content.value, [], 'ieee')
    if (!data?.text) { showExportToast('引用编号失败'); return }
    if (activeTab.value) { setContent(`${data.text}${data.bibliography || ''}`); markDirty() }
    showExportToast(`已编号 ${preview?.unique_count ?? data.citations?.length ?? 0} 条引用`)
  } catch (e) { showExportToast(`引用编号失败：${e}`) }
}

async function handleZoteroInsert() {
  const query = window.prompt('搜索 Zotero')
  if (!query?.trim()) return
  try {
    const status = await getZoteroStatus()
    if (status && status.connected === false) { showExportToast('请先配置 Zotero API'); return }
    const items = await searchZotero(query.trim(), 5)
    const item = items[0]
    if (!item?.key) { showExportToast('未找到 Zotero 结果'); return }
    const citation = item.markdown_citation || (item.citation_key ? `[@${item.citation_key}]` : '')
    if (citation) insertTextAtCursor(citation)
    showExportToast(`已插入 ${item.citation_key || item.key}`)
  } catch (e) { showExportToast(`Zotero 搜索失败：${e}`) }
}

async function handleImageSelected(file: File) {
  try {
    const data = await insertImageFile(file)
    showExportToast(data ? '图片已插入' : '图片上传失败')
  } catch { showExportToast('图片上传失败') }
}

async function handleVisionSelected(file: File) {
  try {
    const data = await analyzeVision(file, 'general')
    if (!data) { showExportToast('Vision 分析失败'); return }
    const findings = data.key_findings?.length ? `\n发现：${data.key_findings.join('; ')}` : ''
    const chart = data.chart_type ? `\n图表类型：${data.chart_type}` : ''
    const table = data.table_data?.length
      ? `\n\n${data.table_data.map((row: string[]) => `| ${row.join(' | ')} |`).join('\n')}`
      : ''
    insertTextAtCursor(`\n\n> Vision：${data.text || data.raw_description || '未返回文本'}${chart}${findings}${table}\n`)
    showExportToast('Vision 结果已插入')
  } catch (e) { showExportToast(`Vision 分析失败：${e}`) }
}

async function runComplianceCheck() {
  if (!content.value.trim()) { complianceError.value = '编辑器内容为空'; showCompliance.value = true; return }
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
      complianceError.value = data.error || '合规检查失败'
    } else if (data.report?.summary) {
      complianceReport.value = data.report
    } else {
      complianceError.value = 'LLM 返回格式异常'
    }
  } catch (e) { complianceError.value = `请求失败：${e}`
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

// 鈹€鈹€ Resize 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
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

// 鈹€鈹€ Keyboard 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
function onKeyDown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); handleSaveFile() }
  if (e.key === 'Tab' && !e.ctrlKey && !e.shiftKey && acceptGhostText()) { e.preventDefault() }
  if (e.key === 'Escape') clearGhostText()
}

// 鈹€鈹€ Lifecycle 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
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

/* 鈹€鈹€ Sidebar 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ */
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
  top: 44px;
  transform: translateX(-50%) rotate(-90deg);
  transform-origin: center;
  width: 104px;
  height: 28px;
  border: 1px solid color-mix(in srgb, var(--border-color) 58%, transparent);
  border-radius: 9px 9px 0 0;
  background: color-mix(in srgb, var(--toolbar-bg) 72%, transparent);
  color: var(--c-text-3);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font: inherit;
  font-size: 11px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  white-space: nowrap;
}
.sidebar-rail-button:hover {
  color: var(--c-accent);
  border-color: var(--c-accent);
  background: color-mix(in srgb, var(--toolbar-bg) 86%, transparent);
}

/* 鈹€鈹€ Editor center 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ */
.layout-editor {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  container-type: inline-size;
}

/* 鈹€鈹€ Right panel 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ */
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

/* 鈹€鈹€ Resize handle 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ */
.resize-handle {
  width: 4px;
  cursor: col-resize;
  background: transparent;
  transition: background 0.15s;
  flex-shrink: 0;
}
.resize-handle:hover { background: var(--c-accent); }

/* 鈹€鈹€ Responsive 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ */
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
