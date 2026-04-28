import { API_BASE } from '../utils/api'

export interface CitationIndexResponse {
  text?: string
  citations?: Array<Record<string, unknown>>
  index?: Record<string, number>
  bibliography?: string
}

export interface CitationExtractResponse {
  keys?: string[]
  unique_count?: number
  index?: Record<string, number>
}

export interface ZoteroStatusResponse {
  connected?: boolean
  user_id?: string
  style?: string
  error?: string
}

export interface ZoteroItem {
  key: string
  citation_key?: string
  title?: string
  authors?: string[]
  year?: string
  journal?: string
  markdown_citation?: string
}

export function useEditorCitation() {
  const API = API_BASE

  async function processCitations(
    targetContent: string,
    bibliography: Record<string, unknown>[] = [],
    style = 'ieee',
  ): Promise<CitationIndexResponse | null> {
    const resp = await fetch(`${API}/api/citation/index`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: targetContent, bibliography, style }),
    })
    if (!resp.ok) return null
    return await resp.json() as CitationIndexResponse
  }

  async function previewCitations(targetContent: string): Promise<CitationExtractResponse | null> {
    const resp = await fetch(`${API}/api/citation/extract?content=${encodeURIComponent(targetContent)}`)
    if (!resp.ok) return null
    return await resp.json() as CitationExtractResponse
  }

  async function getZoteroStatus(): Promise<ZoteroStatusResponse | null> {
    const resp = await fetch(`${API}/api/zotero/status`)
    if (!resp.ok) return null
    return await resp.json() as ZoteroStatusResponse
  }

  async function searchZotero(query: string, limit = 20): Promise<ZoteroItem[]> {
    const resp = await fetch(`${API}/api/zotero/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, limit }),
    })
    if (!resp.ok) return []
    const data = await resp.json() as { items?: ZoteroItem[] }
    return data.items || []
  }

  async function getZoteroItem(key: string): Promise<ZoteroItem | null> {
    const resp = await fetch(`${API}/api/zotero/item/${encodeURIComponent(key)}`)
    if (!resp.ok) return null
    return await resp.json() as ZoteroItem
  }

  async function insertZoteroCitation(key: string): Promise<ZoteroItem | null> {
    const item = await getZoteroItem(key)
    return item
  }

  return { processCitations, previewCitations, getZoteroStatus, searchZotero, getZoteroItem, insertZoteroCitation }
}
