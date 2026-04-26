<template>
  <div class="editor-layout">
    <!-- 宸︿晶鏂囦欢鏍?-->
    <div class="layout-sidebar" :style="{ width: sidebarWidth + 'px' }">
      <FileTree />
    </div>
    <div class="resize-handle sidebar-resize" @mousedown="startResize($event, 'sidebar')"></div>

    <!-- 涓棿缂栬緫鍣?-->
    <div class="layout-editor">
      <MindMapView
        v-if="workspaceMode === 'mindmap'"
        @enter-editor="enterEditorFromMindMap"
      />
      <template v-else>
      <EditorTabs />
      <div v-if="!activeTab" class="editor-welcome">
        <div class="welcome-panel">
          <div class="welcome-kicker">Scholar Workspace</div>
          <h2>开始写作</h2>
          <p>打开一个工程或创建论文草稿，编辑器、预览和 AI 助手会在文档打开后自动进入工作区。</p>
          <div class="welcome-actions">
            <button class="welcome-action primary" @click="showProjectStart = true">新建工程</button>
            <button class="welcome-action" @click="showTemplatePicker = true">新建论文</button>
            <button class="welcome-action" @click="openWorkspaceFolder">打开工程</button>
          </div>
        </div>
      </div>
      <template v-else>
      <div class="editor-toolbar">
        <div class="toolbar-left">
          <button class="toolbar-btn new-paper-btn" @click="showTemplatePicker = true" title="新建论文">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/></svg>
            <span class="btn-label">新建论文</span>
          </button>
          <button class="toolbar-btn" @click="openMindMapFromEditor" title="打开思维导图">思维导图</button>
          <span class="toolbar-hint">Ctrl+K AI Edit</span>
        </div>
        <div class="toolbar-right" @click.stop>
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

          <div class="tool-group">
            <button class="toolbar-btn menu-trigger" :class="{ active: openToolMenu === 'insert' }" @click="toggleToolMenu('insert')" title="插入内容">
              插入
              <span class="chevron">⌄</span>
            </button>
            <div v-if="openToolMenu === 'insert'" class="tool-menu">
              <button class="tool-menu-item" @click="runMenuAction(openImagePicker)" :disabled="assetLoading">图片</button>
              <button class="tool-menu-item" @click="runMenuAction(handleInsertTable)">表格</button>
              <button class="tool-menu-item" @click="runMenuAction(handleInsertInlineFormula)">行内公式</button>
              <button class="tool-menu-item" @click="runMenuAction(handleInsertBlockFormula)">块级公式</button>
            </div>
          </div>

          <div class="tool-group">
            <button class="toolbar-btn menu-trigger" :class="{ active: openToolMenu === 'analyze' }" @click="toggleToolMenu('analyze')" title="分析与检查">
              分析
              <span class="chevron">⌄</span>
            </button>
            <div v-if="openToolMenu === 'analyze'" class="tool-menu">
              <button class="tool-menu-item" @click="runMenuAction(openVisionPicker)" :disabled="assetLoading">OCR / Vision</button>
              <button class="tool-menu-item" @click="runMenuAction(runComplianceCheck)">论文合规检查</button>
              <button class="tool-menu-item" @click="toggleAiPanel">AI 编辑面板</button>
            </div>
          </div>

          <div class="tool-group">
            <button class="toolbar-btn menu-trigger" :class="{ active: openToolMenu === 'reference' }" @click="toggleToolMenu('reference')" title="引用与文献">
              引用
              <span class="chevron">⌄</span>
            </button>
            <div v-if="openToolMenu === 'reference'" class="tool-menu">
              <button class="tool-menu-item" @click="runMenuAction(handleProcessCitations)" :disabled="assetLoading">编号引用</button>
              <button class="tool-menu-item" @click="runMenuAction(handleZoteroInsert)" :disabled="assetLoading">Zotero 搜索</button>
            </div>
          </div>

          <div class="tool-group">
            <button class="toolbar-btn menu-trigger primary-trigger" :class="{ active: openToolMenu === 'export' }" @click="toggleToolMenu('export')" title="导出文档">
              导出
              <span class="chevron">⌄</span>
            </button>
            <div v-if="openToolMenu === 'export'" class="tool-menu export-menu">
              <label v-if="exportTemplates.length" class="tool-menu-label">
                LaTeX 模板
                <select
                  class="export-select"
                  v-model="selectedTemplate"
                  :disabled="exportLoading"
                  title="选择导出模板"
                >
                  <option value="" disabled>选择模板...</option>
                  <option
                    v-for="t in exportTemplates"
                    :key="t.id"
                    :value="t.id"
                  >{{ t.name }}</option>
                </select>
              </label>
              <button class="tool-menu-item" @click="runMenuAction(handleExportWord)" :disabled="exportLoading">Word (.docx)</button>
              <button class="tool-menu-item" @click="runMenuAction(handleExportLatex)" :disabled="!selectedTemplate || exportLoading">LaTeX (.tex)</button>
              <button
                class="tool-menu-item"
                @click="runMenuAction(handleExportPdf)"
                :disabled="!selectedTemplate || exportLoading || !tectonicAvailable"
              >PDF</button>
            </div>
          </div>
          <!-- 瀵煎嚭鐘舵€佹彁绀?-->
          <div v-if="exportMessage" class="export-toast">{{ exportMessage }}</div>
          <button class="toolbar-btn icon-btn" :class="{ active: showPreview }" @click="showPreview = !showPreview" title="切换预览">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
          </button>
          <button class="toolbar-btn icon-btn" @click="handleSaveFile" title="保存 (Ctrl+S)">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
          </button>
        </div>
      </div>
      <MonacoEditor :theme="isDark ? 'vs-dark' : 'vs'" :on-did-change-content="onDidChangeContent" @contentChange="onContentChange" @selectionChange="onSelectionChange" />
      </template>
      </template>
    </div>

    <!-- 鍙充晶闈㈡澘 -->
    <template v-if="workspaceMode === 'editor' && activeTab && (showPreview || showAiPanel)">
      <div class="resize-handle panel-resize" @mousedown="startResize($event, 'panel')"></div>
      <div class="layout-panel" :style="{ width: panelWidth + 'px' }">
        <MarkdownPreview v-if="showPreview" :content="content" :version="contentVersion" :class="{ 'panel-half': showAiPanel }" />
        <AiPanel
          v-if="showAiPanel"
          :editor-context="selection.text || content"
          :can-undo="!!previousContent"
          :workspace-files="workspaceFiles"
          :class="{ 'panel-half': showPreview }"
          @insert="handleInsert"
          @undo="handleUndo"
          @close="showAiPanel = false"
        />
      </div>
    </template>

    <!-- 璁烘枃鍚堣妫€鏌ュ脊绐?-->
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
          <button class="project-start-close" @click="showProjectStart = false">&times;</button>
        </div>
        <div class="project-start-options">
          <button class="project-start-option primary" @click="startProjectInEditor">
            <strong>直接进入编辑器</strong>
            <span>创建空白文档，保持现有写作流程。</span>
          </button>
          <button class="project-start-option" @click="startProjectWithMindMap">
            <strong>先创建思维导图</strong>
            <span>先梳理论文结构，再保存并进入编辑器。</span>
          </button>
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
import ComplianceModal from './ComplianceModal.vue'
import TemplatePicker from './TemplatePicker.vue'
import MindMapView from './MindMapView.vue'
import { useEditor } from '../composables/useEditor'
import { useMindMap } from '../composables/useMindMap'
import { API_BASE } from '../utils/api'
import { readSseStream } from '../utils/streamReader'

const props = defineProps<{ isDark: boolean }>()
const workspaceMode = ref<'editor' | 'mindmap'>('editor')
const showProjectStart = ref(false)
const { resetMindMap, loadSavedMindMap, saveMindMap } = useMindMap()

const {
  content, contentVersion, activeTab, selection,
  showPreview, showAiPanel, aiLoading, aiResult,
  previousContent,
  openNewUntitled, setContent, markDirty,
  saveFile, exportToWord, insertTextAtCursor, insertImageFile, analyzeVision,
  insertTable, insertInlineFormula, insertBlockFormula, processCitations,
  previewCitations, getZoteroStatus, searchZotero, insertZoteroCitation,
  aiEdit, applyAiResult, undoEdit, tabs,
  onDidChangeContent, acceptGhostText, clearGhostText,
} = useEditor()

// 鈹€鈹€ 璁烘枃妯℃澘閫夋嫨鍣?鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
const showTemplatePicker = ref(false)
const workspaceFiles = computed(() =>
  tabs.value.map(t => ({ name: t.title || t.path?.split(/[\\/]/).pop() || 'untitled', content: t.content }))
)
const imageInputRef = ref<HTMLInputElement | null>(null)
const visionInputRef = ref<HTMLInputElement | null>(null)
const assetLoading = ref(false)
const openToolMenu = ref<'insert' | 'analyze' | 'reference' | 'export' | null>(null)

function startProjectInEditor() {
  showProjectStart.value = false
  workspaceMode.value = 'editor'
  openNewUntitled()
}

function startProjectWithMindMap() {
  showProjectStart.value = false
  resetMindMap()
  workspaceMode.value = 'mindmap'
}

function enterEditorFromMindMap() {
  saveMindMap()
  workspaceMode.value = 'editor'
  if (!activeTab.value) openNewUntitled()
}

function openMindMapFromEditor() {
  loadSavedMindMap()
  workspaceMode.value = 'mindmap'
}

function toggleToolMenu(menu: 'insert' | 'analyze' | 'reference' | 'export') {
  openToolMenu.value = openToolMenu.value === menu ? null : menu
}

function closeToolMenu() {
  openToolMenu.value = null
}

function runMenuAction(action: () => void | Promise<void>) {
  closeToolMenu()
  void action()
}

function toggleAiPanel() {
  closeToolMenu()
  showAiPanel.value = !showAiPanel.value
}

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
  //setContent 浼氬湪 nextTick 閫氳繃 tab switch 澶勭悊
  nextTick(() => {
    if (activeTab.value) {
      activeTab.value.content = markdown
      activeTab.value.name = `${templateId}-paper.md`
    }
  })
}

function openImagePicker() {
  imageInputRef.value?.click()
}

function openVisionPicker() {
  visionInputRef.value?.click()
}

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
    if (!data) {
      showExportToast('Vision analysis failed')
      return
    }

    const findings = data.key_findings?.length ? `\nFindings: ${data.key_findings.join('; ')}` : ''
    const chart = data.chart_type ? `\nChart type: ${data.chart_type}` : ''
    const table = data.table_data?.length
      ? `\n\n${data.table_data.map(row => `| ${row.join(' | ')} |`).join('\n')}`
      : ''
    insertTextAtCursor(`\n\n> Vision: ${data.text || data.raw_description || 'No text returned'}${chart}${findings}${table}\n`)
    showExportToast('Vision result inserted')
  } catch (e) {
    showExportToast(`Vision analysis failed: ${e}`)
  } finally {
    assetLoading.value = false
  }
}

function handleInsertTable() {
  insertTable(3, 3)
}

function handleInsertInlineFormula() {
  insertInlineFormula()
}

function handleInsertBlockFormula() {
  insertBlockFormula()
}

async function handleProcessCitations() {
  if (!content.value.trim()) {
    showExportToast('Please write content in the editor first')
    return
  }

  assetLoading.value = true
  try {
    const preview = await previewCitations(content.value)
    const data = await processCitations(content.value, [], 'ieee')
    if (!data?.text) {
      showExportToast('Citation indexing failed')
      return
    }

    if (activeTab.value) {
      setContent(`${data.text}${data.bibliography || ''}`)
      markDirty()
    }
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
    if (status && status.connected === false) {
      showExportToast('Please configure Zotero API first')
      return
    }

    const items = await searchZotero(query.trim(), 5)
    const item = items[0]
    if (!item?.key) {
      showExportToast('No Zotero result found')
      return
    }

    await insertZoteroCitation(item.key)
    showExportToast(`Inserted ${item.citation_key || item.key}`)
  } catch (e) {
    showExportToast(`Zotero search failed: ${e}`)
  } finally {
    assetLoading.value = false
  }
}

// 鈹€鈹€ 璁烘枃鍚堣妫€鏌?鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
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
    if (data.error && !data.report) {
      complianceError.value = data.error || 'Compliance check failed'
    } else {
      complianceReport.value = data.report
      if (data.report?.error && !data.report?.summary) {
        complianceError.value = data.report.error
      }
    }
  } catch (e) {
    complianceError.value = `璇锋眰澶辫触: ${e}`
  } finally {
    complianceLoading.value = false
  }
}

const sidebarWidth = ref(296)
const panelWidth = ref(300)

function onContentChange(_value: string) {
  // content is already updated by useEditor
}

function onSelectionChange(_sel: any) {
  // selection is already updated by useEditor
}

function handleAiEdit(instruction: string, taskType?: string) {
  const contextText = selection.value.text || content.value
  if (!contextText.trim()) {
    // 娌℃湁閫夋嫨鍐呭鏃讹紝鍙敤 instruction 鎻愰棶锛圓I 鍙互鍋?free-form 闂瓟锛?    aiEdit(instruction, '', undefined)
    return
  }
  aiEdit(instruction, contextText, taskType)
}

async function handleAgentRequest(instruction: string) {
  const contextText = selection.value.text || content.value
  try {
    const resp = await fetch(`${EXPORT_API}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: instruction,
        context_text: contextText || undefined,
      }),
    })
    if (resp.ok) {
      // Stream the response to AI result
      const reader = resp.body?.getReader()
      if (!reader) return

      await readSseStream(reader, (_type, evt) => {
        if (evt.content) {
          aiResult.value = (aiResult.value || '') + (evt.content as string)
        }
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
    const resp = await fetch(`${EXPORT_API}/api/paper-style-transfer`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: contextText, template_id: templateId, section: 'introduction' }),
    })
    if (resp.ok) {
      const data = await resp.json()
      // Use aiEdit to set the result as the AI result
      aiEdit(`Rewrite in ${templateName} style`, contextText, 'expand')
    }
  } catch (e) { console.warn('handleStyleTransfer failed:', e) }
}

function handleInsert(text: string) {
  aiResult.value = text
  applyAiResult()
}

function handleUndo() {
  undoEdit()
}

async function handleSaveFile() {
  const err = await saveFile()
  if (err) showExportToast(err)
  else showExportToast('Saved')
}

// Track active resize handlers so onBeforeUnmount can clean them up if drag is in progress
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

// Ctrl+S save, Tab accept ghost text
async function onKeyDown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 's') {
    e.preventDefault()
    try {
      const err = await saveFile()
      if (err) showExportToast(err)
    } catch (err) {
      showExportToast(String(err))
    }
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
  window.addEventListener('click', closeToolMenu)
  loadExportTemplates()
  window.addEventListener('paper-scaffold', handlePaperScaffold)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeyDown)
  window.removeEventListener('click', closeToolMenu)
  window.removeEventListener('paper-scaffold', handlePaperScaffold)
  // Clean up resize drag handlers if a drag was in progress when component unmounted
  if (_activeResizeMove) document.removeEventListener('mousemove', _activeResizeMove)
  if (_activeResizeUp) document.removeEventListener('mouseup', _activeResizeUp)
})

// 鈹€鈹€ Pandoc 瀵煎嚭 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
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
  if (!content.value.trim()) {
    showExportToast('Please write content in the editor first')
    return
  }

  exportLoading.value = true
  try {
    const resp = await fetch(`${EXPORT_API}/api/export`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        markdown: content.value,
        template_id: selectedTemplate.value,
      }),
    })

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ error: '瀵煎嚭澶辫触' }))
      showExportToast(err.error || '瀵煎嚭澶辫触')
      return
    }

    const data = await resp.json()
    const tex = data.tex || ''

    if (!tex) {
      showExportToast('杞崲缁撴灉涓虹┖')
      return
    }

    await navigator.clipboard.writeText(tex)
    showExportToast('LaTeX copied to clipboard')
  } catch (e) {
    showExportToast(`瀵煎嚭澶辫触: ${e}`)
  } finally {
    exportLoading.value = false
  }
}

async function handleExportPdf() {
  if (!selectedTemplate.value || exportLoading.value) return
  if (!content.value.trim()) {
    showExportToast('Please write content in the editor first')
    return
  }
  if (!tectonicAvailable.value) {
    showExportToast('Please install the LaTeX engine (Tectonic) first')
    return
  }

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
      const err = await resp.json().catch(() => ({ detail: 'PDF 瀵煎嚭澶辫触' }))
      showExportToast(err.detail || err.error || 'PDF 瀵煎嚭澶辫触')
      return
    }

    // 涓嬭浇 PDF
    const blob = await resp.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const cd = resp.headers.get('content-disposition')
    const match = cd?.match(/filename="?([^"]+)"?/)
    a.download = match ? match[1] : 'paper.pdf'
    a.click()
    URL.revokeObjectURL(url)
    showExportToast('PDF downloaded')
  } catch (e) {
    showExportToast(`PDF 瀵煎嚭澶辫触: ${e}`)
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

.layout-sidebar {
  flex-shrink: 0;
  min-width: 0;
  overflow: hidden;
}

@media (max-width: 1180px) {
  .layout-sidebar {
    width: 220px !important;
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
  .layout-panel,
  .panel-resize {
    display: none;
  }
}

@media (max-width: 760px) {
  .editor-welcome {
    padding: 24px;
  }

  .welcome-panel {
    width: 100%;
  }

  .editor-toolbar {
    gap: 6px;
    padding-inline: 8px;
  }

  .toolbar-hint {
    display: none;
  }
}

.layout-editor {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  container-type: inline-size;
}

.editor-welcome {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px;
  background: var(--editor-bg);
}

.welcome-panel {
  width: min(520px, 100%);
  color: var(--text-primary);
}

.welcome-kicker {
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.welcome-panel h2 {
  margin: 10px 0 8px;
  font-size: 28px;
  font-weight: 700;
}

.welcome-panel p {
  margin: 0 0 22px;
  color: var(--text-secondary);
  line-height: 1.7;
  font-size: 14px;
}

.welcome-actions {
  display: grid;
  gap: 10px;
}

.welcome-action {
  height: 38px;
  border: 1px solid var(--border-color);
  border-radius: 7px;
  background: var(--toolbar-bg);
  color: var(--text-primary);
  font: inherit;
  font-size: 13px;
  cursor: pointer;
  text-align: left;
  padding: 0 14px;
}
.welcome-action:hover { background: var(--hover-bg); border-color: var(--accent); }
.welcome-action.primary {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
  font-weight: 650;
}

.project-start-backdrop {
  position: fixed;
  inset: 0;
  z-index: 80;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.42);
}
.project-start-dialog {
  width: min(520px, calc(100vw - 48px));
  border: 1px solid var(--border-color);
  border-radius: 10px;
  background: var(--panel-bg);
  color: var(--text-primary);
  box-shadow: 0 24px 72px rgba(0, 0, 0, 0.35);
}
.project-start-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  padding: 18px 20px;
  border-bottom: 1px solid var(--border-color);
}
.project-start-header h3 {
  margin: 4px 0 0;
  font-size: 20px;
}
.project-start-close {
  border: 0;
  background: transparent;
  color: var(--text-secondary);
  font-size: 24px;
  line-height: 1;
  cursor: pointer;
}
.project-start-options {
  display: grid;
  gap: 10px;
  padding: 18px 20px 20px;
}
.project-start-option {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--toolbar-bg);
  color: var(--text-primary);
  text-align: left;
  padding: 14px 16px;
  cursor: pointer;
  font: inherit;
}
.project-start-option:hover {
  border-color: var(--accent);
  background: var(--hover-bg);
}
.project-start-option.primary {
  background: color-mix(in srgb, var(--accent) 18%, var(--toolbar-bg));
  border-color: color-mix(in srgb, var(--accent) 55%, var(--border-color));
}
.project-start-option strong {
  display: block;
  margin-bottom: 5px;
  font-size: 14px;
}
.project-start-option span {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.layout-panel {
  flex: 0 1 auto;
  min-width: 260px;
  max-width: min(760px, 45vw);
  overflow: hidden;
}

.resize-handle {
  width: 4px;
  cursor: col-resize;
  background: transparent;
  transition: background 0.15s;
  flex-shrink: 0;
}
.resize-handle:hover { background: var(--accent); }

.editor-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: nowrap;
  gap: 12px;
  padding: 7px 12px;
  border-bottom: 1px solid var(--border-color);
  background: var(--toolbar-bg);
  min-height: 46px;
  flex-shrink: 0;
  overflow: hidden;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 0 1 auto;
}
.toolbar-right {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  min-width: 0;
  flex: 1 1 auto;
  overflow: visible;
}

.file-name {
  font-size: 13px;
  color: var(--text-primary);
}
.file-modified {
  color: var(--accent);
  font-weight: bold;
}

.toolbar-btn {
  height: 28px;
  background: transparent;
  border: 1px solid transparent;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 0 8px;
  border-radius: 6px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-family: inherit;
  line-height: 1;
  white-space: nowrap;
  flex-shrink: 0;
}
.toolbar-btn:hover { background: var(--hover-bg); color: var(--text-primary); border-color: var(--border-color); }
.toolbar-btn.active { color: var(--text-primary); background: var(--active-bg); border-color: var(--border-color); }
.toolbar-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.icon-btn {
  width: 28px;
  padding: 0;
  justify-content: center;
}

.hidden-file-input {
  display: none;
}

.new-paper-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--accent);
  font-weight: 650;
  max-width: 108px;
}
.new-paper-btn .btn-label {
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.new-paper-btn:hover { background: var(--hover-bg); border-color: var(--accent); }

.toolbar-hint {
  font-size: 11px;
  color: var(--text-secondary);
  background: var(--code-bg);
  border: 1px solid var(--border-color);
  padding: 3px 8px;
  border-radius: 6px;
  white-space: nowrap;
}

.tool-group {
  position: relative;
  flex-shrink: 0;
}

.menu-trigger {
  min-width: 54px;
  justify-content: center;
}

.primary-trigger {
  color: var(--accent);
  border-color: var(--border-color);
  background: var(--code-bg);
}

.chevron {
  color: var(--text-secondary);
  font-size: 12px;
}

.tool-menu {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  z-index: 40;
  width: 180px;
  padding: 6px;
  background: var(--panel-bg);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  box-shadow: 0 16px 46px rgba(0, 0, 0, 0.28);
}

.export-menu {
  width: 220px;
}

.tool-menu-item {
  width: 100%;
  min-height: 30px;
  display: flex;
  align-items: center;
  padding: 0 10px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-primary);
  text-align: left;
  cursor: pointer;
  font: inherit;
  font-size: 12px;
}
.tool-menu-item:hover:not(:disabled) { background: var(--hover-bg); color: var(--text-primary); }
.tool-menu-item:disabled { opacity: 0.45; cursor: not-allowed; }

.tool-menu-label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 6px 8px 8px;
  color: var(--text-secondary);
  font-size: 11px;
}

.export-select {
  width: 100%;
  background: var(--code-bg);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 12px;
  padding: 6px 8px;
  cursor: pointer;
  outline: none;
}
.export-select:hover { border-color: var(--accent); }
.export-select:disabled { opacity: 0.5; cursor: not-allowed; }
.export-select option { background: var(--panel-bg); }

.export-toast {
  font-size: 12px;
  color: #8ee59d;
  padding: 4px 8px;
  border-radius: 6px;
  background: rgba(34, 197, 94, 0.12);
  border: 1px solid rgba(34, 197, 94, 0.26);
  white-space: nowrap;
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.panel-half {
  height: 50% !important;
  flex: none !important;
}

@container (max-width: 640px) {
  .editor-toolbar {
    gap: 8px;
    padding-inline: 8px;
    height: auto;
    flex-wrap: wrap;
    align-content: center;
  }

  .toolbar-hint {
    display: none;
  }

  .toolbar-left,
  .toolbar-right {
    gap: 4px;
    flex: 1 1 100%;
    justify-content: flex-start;
  }

  .toolbar-right {
    overflow-x: auto;
    scrollbar-width: none;
  }

  .toolbar-right::-webkit-scrollbar {
    display: none;
  }
}

@container (max-width: 520px) {
  .new-paper-btn {
    width: 30px;
    padding: 0;
    justify-content: center;
  }

  .new-paper-btn .btn-label {
    display: none;
  }

  .menu-trigger {
    min-width: 48px;
    padding: 0 6px;
  }

  .icon-btn {
    width: 26px;
  }
}
</style>
