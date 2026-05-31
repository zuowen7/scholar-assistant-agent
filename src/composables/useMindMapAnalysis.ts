import { API_BASE } from '../utils/api'
import type { MindMapData } from './useMindMap'
import { i18n } from '../i18n'

export type MindMapIssueType =
  | 'isolated'
  | 'duplicate'
  | 'logic_gap'
  | 'shallow_branch'
  | 'weak_link'
  | 'missing_support'

export type MindMapIssueSeverity = 'info' | 'warning' | 'critical'

export interface MindMapAnalysisIssue {
  id: string
  type: MindMapIssueType
  severity: MindMapIssueSeverity
  title: string
  message: string
  nodeIds: string[]
}

export function useMindMapAnalysis() {
  async function analyzeMindMap(map: MindMapData): Promise<MindMapAnalysisIssue[]> {
    const raw = await callBackendAnalysis(map)
    return raw.map(iss => ({
      id: iss.id ?? `issue-${Math.random().toString(16).slice(2, 8)}`,
      type: (iss.type as MindMapIssueType) ?? 'logic_gap',
      severity: (iss.severity as MindMapIssueSeverity) ?? 'info',
      title: String(iss.title ?? ''),
      message: String(iss.message ?? ''),
      nodeIds: resolveNodeIds(iss.node_texts ?? [], map),
    }))
  }

  return { analyzeMindMap }
}

async function callBackendAnalysis(
  map: MindMapData,
): Promise<Array<Record<string, any>>> {
  try {
    const res = await fetch(`${API_BASE}/api/mindmap/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        root_id: map.rootId,
        nodes: map.nodes,
        links: map.links,
      }),
    })
    if (!res.ok) return runStructuralFallback(map)
    const data = await res.json()
    if (Array.isArray(data.issues) && data.issues.length > 0) return data.issues
    return runStructuralFallback(map)
  }
  catch {
    return runStructuralFallback(map)
  }
}

function resolveNodeIds(texts: string[], map: MindMapData): string[] {
  if (!texts || !texts.length) return []
  const ids: string[] = []
  for (const text of texts) {
    for (const [id, node] of Object.entries(map.nodes)) {
      if (node.text.trim() === text.trim()) {
        ids.push(id)
        break
      }
    }
  }
  return ids
}

function getGenericNames(): Set<string> {
  return new Set([i18n.global.t('mindmap.centralTopic'), i18n.global.t('mindmap.newNode'), i18n.global.t('mindmap.unnamedNode')])
}

function runStructuralFallback(map: MindMapData): Array<Record<string, any>> {
  const issues: Array<Record<string, any>> = []
  const root = map.nodes[map.rootId]

  if (root && root.children.length === 0) {
    issues.push({
      id: `issue-${issues.length + 1}`,
      type: 'shallow_branch',
      severity: 'warning',
      title: i18n.global.t('mindmap.analysis.mainChainNotExpanded'),
      message: i18n.global.t('mindmap.analysis.mainChainHint'),
      node_texts: [root.text],
    })
  }

  const normalized = new Map<string, string[]>()
  for (const [id, node] of Object.entries(map.nodes)) {
    const key = node.text.trim().toLowerCase().replace(/\s+/g, '')
    if (!key || getGenericNames().has(key)) continue
    normalized.set(key, [...(normalized.get(key) ?? []), id])
  }
  for (const [text, ids] of normalized) {
    if (ids.length > 1) {
      issues.push({
        id: `issue-${issues.length + 1}`,
        type: 'duplicate',
        severity: 'warning',
        title: i18n.global.t('mindmap.analysis.similarExpression'),
        message: i18n.global.t('mindmap.analysis.similarHint', { count: ids.length }),
        node_texts: ids.map(id => map.nodes[id]?.text ?? text),
      })
    }
  }

  for (const [id, node] of Object.entries(map.nodes)) {
    if (id === map.rootId) continue
    if (node.parentId && !map.nodes[node.parentId]) {
      issues.push({
        id: `issue-${issues.length + 1}`,
        type: 'isolated',
        severity: 'critical',
        title: i18n.global.t('mindmap.analysis.orphanNode'),
        message: i18n.global.t('mindmap.analysis.orphanHint'),
        node_texts: [node.text],
      })
    }
    if (!node.children.length && (node.text.trim().length < 6 || getGenericNames().has(node.text.trim()))) {
      issues.push({
        id: `issue-${issues.length + 1}`,
        type: 'missing_support',
        severity: 'info',
        title: i18n.global.t('mindmap.analysis.suggestSupport'),
        message: i18n.global.t('mindmap.analysis.suggestSupportHint'),
        node_texts: [node.text],
      })
    }
  }

  return issues.slice(0, 12)
}
