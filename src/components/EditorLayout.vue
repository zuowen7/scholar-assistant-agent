<template>
  <div class="editor-layout">
    <!-- 左侧文件树 -->
    <div class="layout-sidebar" :style="{ width: sidebarWidth + 'px' }">
      <FileTree />
    </div>
    <div class="resize-handle" @mousedown="startResize($event, 'sidebar')"></div>

    <!-- 中间编辑器 -->
    <div class="layout-editor">
      <!-- 文件标签栏 -->
      <EditorTabs />
      <!-- 编辑器工具栏 -->
      <div class="editor-toolbar">
        <div class="toolbar-left">
          <button class="toolbar-btn new-paper-btn" @click="showTemplatePicker = true" title="新建论文">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/></svg>
            <span class="btn-label">新建论文</span>
          </button>
          <span class="toolbar-hint">Ctrl+K AI Edit</span>
        </div>
        <div class="toolbar-right">
          <!-- 论文合规检查 -->
          <button class="toolbar-btn compliance-btn" @click="runComplianceCheck" title="论文合规检查">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/>
            </svg>
          </button>
          <!-- 导出按钮 -->
          <div class="export-wrapper" v-if="exportTemplates.length">
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
            <button class="export-btn" @click="handleExportLatex" :disabled="!selectedTemplate || exportLoading" title="导出 LaTeX (.tex)">LaTeX</button>
            <button
              class="export-btn pdf-btn"
              @click="handleExportPdf"
              :disabled="!selectedTemplate || exportLoading || !tectonicAvailable"
              :title="tectonicAvailable ? '导出 PDF' : '请先安装 LaTeX 引擎（Tectonic）'"
            >PDF</button>
          </div>
          <!-- 导出状态提示 -->
          <div v-if="exportMessage" class="export-toast">{{ exportMessage }}</div>
          <button class="toolbar-btn" :class="{ active: showPreview }" @click="showPreview = !showPreview" title="Toggle Preview">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
          </button>
          <button class="toolbar-btn" :class="{ active: showAiPanel }" @click="showAiPanel = !showAiPanel" title="AI Panel">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a10 10 0 0110 10 10 10 0 01-10 10A10 10 0 012 12 10 10 0 0112 2z"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/></svg>
          </button>
          <button class="toolbar-btn" @click="saveFile" title="Save (Ctrl+S)">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
          </button>
        </div>
      </div>
      <!-- Monaco 编辑器 -->
      <MonacoEditor :theme="isDark ? 'vs-dark' : 'vs'" @contentChange="onContentChange" @selectionChange="onSelectionChange" />
    </div>

    <!-- 右侧面板 -->
    <template v-if="showPreview || showAiPanel">
      <div class="resize-handle" @mousedown="startResize($event, 'panel')"></div>
      <div class="layout-panel" :style="{ width: panelWidth + 'px' }">
        <MarkdownPreview v-if="showPreview" :content="content" :version="contentVersion" :class="{ 'panel-half': showAiPanel }" />
        <AiPanel
          v-if="showAiPanel"
          :loading="aiLoading"
          :result="aiResult"
          :can-undo="!!previousContent"
          :class="{ 'panel-half': showPreview }"
          @edit="handleAiEdit"
          @accept="applyAiResult"
          @reject="rejectAiResult"
          @undo="handleUndo"
          @cancel="cancelAiEdit"
          @close="showAiPanel = false"
          @styleTransfer="handleStyleTransfer"
          @agent="handleAgentRequest"
        />
      </div>
    </template>

    <!-- 论文合规检查弹窗 -->
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
      @close="showTemplatePicker = false"
      @create="handleScaffoldCreate"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
import MonacoEditor from './MonacoEditor.vue'
import MarkdownPreview from './MarkdownPreview.vue'
import FileTree from './FileTree.vue'
import EditorTabs from './EditorTabs.vue'
import AiPanel from './AiPanel.vue'
import ComplianceModal from './ComplianceModal.vue'
import TemplatePicker from './TemplatePicker.vue'
import { useEditor } from '../composables/useEditor'

const props = defineProps<{ isDark: boolean }>()

const {
  content, contentVersion, activeTab, selection,
  showPreview, showAiPanel, aiLoading, aiResult,
  previousContent,
  openNewUntitled,
  saveFile, aiEdit, cancelAiEdit, applyAiResult, rejectAiResult, undoEdit,
} = useEditor()

// ── 论文模板选择器 ──────────────────────────────────────────────
const showTemplatePicker = ref(false)

function handleScaffoldCreate(markdown: string, templateId: string) {
  openNewUntitled()
  //setContent 会在 nextTick 通过 tab switch 处理
  nextTick(() => {
    if (activeTab.value) {
      activeTab.value.content = markdown
      activeTab.value.name = `${templateId}-paper.md`
    }
  })
}

// ── 论文合规检查 ────────────────────────────────────────────────
const showCompliance = ref(false)
const complianceLoading = ref(false)
const complianceError = ref('')
const complianceReport = ref<Record<string, unknown> | null>(null)

async function runComplianceCheck() {
  if (!content.value.trim()) {
    complianceError.value = '编辑器内容为空'
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
      complianceError.value = data.error || '检查失败'
    } else {
      complianceReport.value = data.report
      if (data.report?.error && !data.report?.summary) {
        complianceError.value = data.report.error
      }
    }
  } catch (e) {
    complianceError.value = `请求失败: ${e}`
  } finally {
    complianceLoading.value = false
  }
}

const sidebarWidth = ref(200)
const panelWidth = ref(400)

function onContentChange(_value: string) {
  // content is already updated by useEditor
}

function onSelectionChange(_sel: any) {
  // selection is already updated by useEditor
}

function handleAiEdit(instruction: string, taskType?: string) {
  const contextText = selection.value.text || content.value
  if (!contextText.trim()) {
    // 没有选择内容时，只用 instruction 提问（AI 可以做 free-form 问答）
    aiEdit(instruction, '', undefined)
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
        context: contextText,
      }),
    })
    if (resp.ok) {
      // Stream the response to AI result
      const reader = resp.body?.getReader()
      if (!reader) return
      const decoder = new TextDecoder()
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const raw = line.slice(6).trim()
          if (!raw) continue
          try {
            const evt = JSON.parse(raw)
            if (evt.content) {
              aiResult.value = (aiResult.value || '') + evt.content
            }
          } catch { /* SSE parse error, skip */ }
        }
      }
    }
  } catch (e) { console.warn('handleAgentRequest failed:', e) }
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

function handleUndo() {
  undoEdit()
}

// 拖拽分隔条
function startResize(e: MouseEvent, target: 'sidebar' | 'panel') {
  e.preventDefault()
  const startX = e.clientX
  const startWidth = target === 'sidebar' ? sidebarWidth.value : panelWidth.value

  function onMouseMove(e: MouseEvent) {
    if (target === 'sidebar') {
      sidebarWidth.value = Math.max(150, Math.min(400, startWidth + e.clientX - startX))
    } else {
      panelWidth.value = Math.max(250, Math.min(800, startWidth - (e.clientX - startX)))
    }
  }

  function onMouseUp() {
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onMouseUp)
  }

  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', onMouseUp)
}

// Ctrl+S 保存
async function onKeyDown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 's') {
    e.preventDefault()
    const err = await saveFile()
    if (err) showExportToast(err)
  }
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
})

// ── Pandoc 导出 ───────────────────────────────────────────────
const isTauri = '__TAURI_INTERNALS__' in window
const EXPORT_API = isTauri ? 'http://localhost:18088' : ''
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
    showExportToast('请先在编辑器中写入内容')
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
      const err = await resp.json().catch(() => ({ error: '导出失败' }))
      showExportToast(err.error || '导出失败')
      return
    }

    const data = await resp.json()
    const tex = data.tex || ''

    if (!tex) {
      showExportToast('转换结果为空')
      return
    }

    await navigator.clipboard.writeText(tex)
    showExportToast('✓ .tex 已复制到剪贴板')
  } catch (e) {
    showExportToast(`导出失败: ${e}`)
  } finally {
    exportLoading.value = false
  }
}

async function handleExportPdf() {
  if (!selectedTemplate.value || exportLoading.value) return
  if (!content.value.trim()) {
    showExportToast('请先在编辑器中写入内容')
    return
  }
  if (!tectonicAvailable.value) {
    showExportToast('请先安装 LaTeX 引擎（在设置中安装 Tectonic）')
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
      const err = await resp.json().catch(() => ({ detail: 'PDF 导出失败' }))
      showExportToast(err.detail || err.error || 'PDF 导出失败')
      return
    }

    // 下载 PDF
    const blob = await resp.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const cd = resp.headers.get('content-disposition')
    const match = cd?.match(/filename="?([^"]+)"?/)
    a.download = match ? match[1] : 'paper.pdf'
    a.click()
    URL.revokeObjectURL(url)
    showExportToast('✓ PDF 已下载')
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
  background: var(--editor-bg);
  color: var(--text-primary);
}

.layout-sidebar {
  flex-shrink: 0;
  overflow: hidden;
}

.layout-editor {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.layout-panel {
  flex-shrink: 0;
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
  padding: 4px 12px;
  border-bottom: 1px solid var(--border-color);
  background: var(--toolbar-bg);
  min-height: 36px;
}

.toolbar-left { display: flex; align-items: center; gap: 4px; }
.toolbar-right { display: flex; align-items: center; gap: 4px; }

.file-name {
  font-size: 13px;
  color: var(--text-primary);
}
.file-modified {
  color: var(--accent);
  font-weight: bold;
}

.toolbar-btn {
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 4px 6px;
  border-radius: 4px;
  display: flex;
  align-items: center;
}
.toolbar-btn:hover { background: var(--hover-bg); color: var(--text-primary); }
.toolbar-btn.active { color: var(--accent); }
.compliance-btn:hover { color: var(--green); }

.new-paper-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--accent);
  font-weight: 500;
}
.new-paper-btn .btn-label { font-size: 12px; }
.new-paper-btn:hover { background: var(--hover-bg); }

.toolbar-hint {
  font-size: 11px;
  color: var(--text-secondary);
  background: rgba(255,255,255,0.05);
  padding: 2px 8px;
  border-radius: 3px;
  margin-left: 8px;
}

.export-wrapper {
  position: relative;
  display: flex;
  align-items: center;
  gap: 2px;
}

.export-btn {
  padding: 3px 8px;
  font-size: 11px;
  font-weight: 600;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s;
}
.export-btn:hover:not(:disabled) { background: var(--hover-bg); color: var(--text-primary); border-color: var(--accent); }
.export-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.pdf-btn:hover:not(:disabled) { color: #ef4444; border-color: #ef4444; }

.export-select {
  background: var(--code-bg);
  border: 1px solid var(--border-color);
  border-radius: 4px;
  color: var(--text-secondary);
  font-size: 12px;
  padding: 3px 8px;
  cursor: pointer;
  outline: none;
  max-width: 140px;
}
.export-select:hover { border-color: var(--accent); color: var(--text-primary); }
.export-select:disabled { opacity: 0.5; cursor: not-allowed; }
.export-select option { background: var(--panel-bg); }

.export-toast {
  font-size: 12px;
  color: #4caf50;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(76, 175, 80, 0.15);
  border: 1px solid rgba(76, 175, 80, 0.3);
  white-space: nowrap;
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.panel-half {
  height: 50% !important;
  flex: none !important;
}
</style>
