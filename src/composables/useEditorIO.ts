import { API_BASE } from '../utils/api'
import { i18n } from '../i18n'

export interface WordExportResponse {
  filename?: string
}

export async function saveBlob(blob: Blob, defaultName: string): Promise<string | null> {
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
    const { open } = await import('@tauri-apps/plugin-shell')
    open(path)
    return null
  } catch (e) {
    console.warn('Tauri save failed:', e)
  }
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

export function useEditorIO() {
  const API = API_BASE

  async function exportToWord(markdown: string, title: string): Promise<string | null> {
    const resp = await fetch(`${API}/api/export/word`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: markdown, title }),
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: 'Word export failed' }))
      return err.detail || err.error || 'Word export failed'
    }
    const data = await resp.json() as WordExportResponse
    if (!data.filename) return 'Word export did not return a filename'
    const downloadResp = await fetch(`${API}/api/export/word/${encodeURIComponent(data.filename)}`)
    if (!downloadResp.ok) return 'Failed to download Word file'
    const blob = await downloadResp.blob()
    return await saveBlob(blob, data.filename || 'export.docx')
  }

  async function exportLatex(markdown: string, templateId: string): Promise<{ tex: string; error?: string }> {
    const resp = await fetch(`${API}/api/export`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ markdown, template_id: templateId }),
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ error: i18n.global.t('errors.exportFailed') }))
      return { tex: '', error: err.error || i18n.global.t('errors.exportFailed') }
    }
    const data = await resp.json()
    return { tex: data.tex || '' }
  }

  async function exportPdf(
    markdown: string,
    templateId: string,
    title: string,
  ): Promise<string | null> {
    const resp = await fetch(`${API}/api/export/pdf`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ markdown, template_id: templateId, title }),
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: i18n.global.t('errors.exportFailed') }))
      return err.detail || err.error || i18n.global.t('errors.exportFailed')
    }
    const blob = await resp.blob()
    return await saveBlob(blob, 'paper.pdf')
  }

  async function loadExportTemplates() {
    const resp = await fetch(`${API}/api/export/templates`)
    if (!resp.ok) return { templates: [], tectonic_available: false }
    const data = await resp.json()
    return {
      templates: data.templates || [],
      tectonic_available: data.tectonic_available || false,
    }
  }

  return { exportToWord, exportLatex, exportPdf, loadExportTemplates, saveBlob }
}
