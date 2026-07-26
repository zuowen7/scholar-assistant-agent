import { computed, ref } from 'vue'
import { API_BASE } from '../utils/api'
import { useEditorIO } from './useEditorIO'
import { useEditorState } from './useEditorState'
import { useFileTree } from './useFileTree'

export type ExportFormat = 'word' | 'latex' | 'pdf'
export type ExportRecordStatus = 'success' | 'failed' | 'cancelled'

export interface ExportTemplate {
  id: string
  name: string
}

export interface ExportCheck {
  id: string
  level: 'pass' | 'warning' | 'error'
  label: string
}

export interface ExportRecord {
  id: string
  title: string
  format: ExportFormat
  template_id: string | null
  status: ExportRecordStatus
  message: string
  created_at: string
}

export interface HumanizedExportError {
  summary: string
  detail: string
  actionable: boolean
}

const format = ref<ExportFormat>('pdf')
const templateId = ref('')
const templates = ref<ExportTemplate[]>([])
const tectonicAvailable = ref(false)
const loading = ref(false)
const previewTex = ref('')
const previewMessage = ref('')
const lastError = ref<HumanizedExportError | null>(null)
const history = ref<ExportRecord[]>([])

export function analyzeExportReadiness(markdown: string): ExportCheck[] {
  const text = markdown.trim()
  const checks: ExportCheck[] = []
  checks.push({
    id: 'content',
    level: text ? 'pass' : 'error',
    label: text ? '文稿内容可用' : '文稿为空，无法导出',
  })
  checks.push({
    id: 'title',
    level: /^#\s+\S+/m.test(markdown) ? 'pass' : 'warning',
    label: /^#\s+\S+/m.test(markdown) ? '已找到论文标题' : '未找到一级标题',
  })
  checks.push({
    id: 'abstract',
    level: /^#{1,3}\s+(abstract|摘要)(?:\s|$)/im.test(markdown) ? 'pass' : 'warning',
    label: /^#{1,3}\s+(abstract|摘要)(?:\s|$)/im.test(markdown) ? '已找到摘要' : '未找到摘要章节',
  })
  const emptyImageAlts = (markdown.match(/!\[\]\([^)]+\)/g) || []).length
  checks.push({
    id: 'image-alt',
    level: emptyImageAlts ? 'warning' : 'pass',
    label: emptyImageAlts ? `${emptyImageAlts} 张图片缺少说明` : '图片说明检查通过',
  })
  const unresolved = (markdown.match(/\{\{cite(?::[^}]+)?\}\}|\[\?\]/gi) || []).length
  checks.push({
    id: 'citations',
    level: unresolved ? 'error' : 'pass',
    label: unresolved ? `${unresolved} 个引用占位符尚未解决` : '未发现引用占位符',
  })
  return checks
}

export function humanizeExportError(error: string): HumanizedExportError {
  const detail = error.trim() || '未知导出错误'
  const missingFile = detail.match(
    /(?:file|image)?\s*['"]?([^'"\s]+\.(?:png|jpe?g|pdf|svg))['"]?.*(?:not found|missing)/i,
  )
  if (missingFile) {
    return {
      summary: `资源文件 ${missingFile[1]} 未找到`,
      detail,
      actionable: true,
    }
  }
  if (/tectonic|latex.*(?:not installed|unavailable)/i.test(detail)) {
    return {
      summary: 'PDF 编译器尚未安装或不可用',
      detail,
      actionable: false,
    }
  }
  if (/undefined control sequence/i.test(detail)) {
    return {
      summary: 'LaTeX 命令无法识别',
      detail,
      actionable: true,
    }
  }
  return { summary: '导出失败', detail, actionable: true }
}

function documentTitle(content: string, fallback: string): string {
  return content.match(/^#\s+(.+)$/m)?.[1]?.trim() || fallback.replace(/\.[^.]+$/, '') || 'paper'
}

export function useExportWorkspace() {
  const editor = useEditorState()
  const { rootDir } = useFileTree()
  const io = useEditorIO()

  const checks = computed(() => analyzeExportReadiness(editor.content.value))
  const blockingIssues = computed(() => checks.value.filter((check) => check.level === 'error'))
  const title = computed(() =>
    documentTitle(editor.content.value, editor.activeTab.value?.name || 'paper'),
  )

  async function load(): Promise<void> {
    const [{ templates: loadedTemplates, tectonic_available }] = await Promise.all([
      io.loadExportTemplates(),
      loadHistory(),
    ])
    templates.value = loadedTemplates
    tectonicAvailable.value = tectonic_available
    if (!templateId.value && loadedTemplates.length) templateId.value = loadedTemplates[0].id
  }

  async function loadHistory(): Promise<void> {
    if (!rootDir.value) {
      history.value = []
      return
    }
    try {
      const response = await fetch(
        `${API_BASE}/api/project/exports?project_path=${encodeURIComponent(rootDir.value)}`,
      )
      if (!response.ok) return
      const payload = (await response.json()) as { records?: ExportRecord[] }
      history.value = Array.isArray(payload.records) ? payload.records : []
    } catch {
      // Export remains usable if optional history loading fails.
    }
  }

  async function record(status: ExportRecordStatus, message: string): Promise<void> {
    if (!rootDir.value) return
    try {
      const response = await fetch(`${API_BASE}/api/project/exports`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_path: rootDir.value,
          title: title.value,
          format: format.value,
          template_id: format.value === 'word' ? null : templateId.value || null,
          status,
          message,
        }),
      })
      if (response.ok) history.value.unshift((await response.json()) as ExportRecord)
    } catch {
      // A history write must never turn a successful file export into a failure.
    }
  }

  async function generatePreview(): Promise<void> {
    previewTex.value = ''
    previewMessage.value = ''
    lastError.value = null
    if (blockingIssues.value.length) {
      lastError.value = humanizeExportError(blockingIssues.value[0].label)
      return
    }
    if (format.value !== 'latex') {
      previewMessage.value = '预检已完成；Word/PDF 将在导出时生成最终文件。'
      return
    }
    if (!templateId.value) {
      lastError.value = humanizeExportError('请选择投稿模板')
      return
    }
    loading.value = true
    try {
      const result = await io.exportLatex(editor.content.value, templateId.value)
      if (result.error) lastError.value = humanizeExportError(result.error)
      else previewTex.value = result.tex
    } finally {
      loading.value = false
    }
  }

  async function runExport(): Promise<boolean> {
    lastError.value = null
    if (blockingIssues.value.length) {
      lastError.value = humanizeExportError(blockingIssues.value[0].label)
      return false
    }
    if (format.value !== 'word' && !templateId.value) {
      lastError.value = humanizeExportError('请选择投稿模板')
      return false
    }
    loading.value = true
    try {
      let error: string | null = null
      if (format.value === 'word') {
        error = await io.exportToWord(editor.content.value, title.value)
      } else if (format.value === 'latex') {
        const result = await io.exportLatex(editor.content.value, templateId.value)
        if (result.error) error = result.error
        else
          error = await io.saveBlob(
            new Blob([result.tex], { type: 'text/x-tex;charset=utf-8' }),
            `${title.value}.tex`,
          )
      } else {
        if (!tectonicAvailable.value) {
          error = 'Tectonic LaTeX compiler unavailable'
        } else {
          error = await io.exportPdf(editor.content.value, templateId.value, title.value)
        }
      }

      if (error === 'Cancelled') {
        await record('cancelled', '用户取消保存')
        return false
      }
      if (error) {
        lastError.value = humanizeExportError(error)
        await record('failed', lastError.value.summary)
        return false
      }
      await record('success', '导出完成')
      return true
    } catch (cause) {
      lastError.value = humanizeExportError(cause instanceof Error ? cause.message : String(cause))
      await record('failed', lastError.value.summary)
      return false
    } finally {
      loading.value = false
    }
  }

  return {
    format,
    templateId,
    templates,
    tectonicAvailable,
    loading,
    previewTex,
    previewMessage,
    lastError,
    history,
    checks,
    blockingIssues,
    title,
    load,
    loadHistory,
    generatePreview,
    runExport,
  }
}

export function _resetExportWorkspaceForTesting() {
  format.value = 'pdf'
  templateId.value = ''
  templates.value = []
  tectonicAvailable.value = false
  loading.value = false
  previewTex.value = ''
  previewMessage.value = ''
  lastError.value = null
  history.value = []
}
