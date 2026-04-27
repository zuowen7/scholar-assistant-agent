import { API_BASE } from '../utils/api'
import type { MindMapData } from './useMindMap'

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

const GENERIC = new Set(['中心主题', '新节点', '未命名节点'])

function runStructuralFallback(map: MindMapData): Array<Record<string, any>> {
  const issues: Array<Record<string, any>> = []
  const root = map.nodes[map.rootId]

  if (root && root.children.length === 0) {
    issues.push({
      id: `issue-${issues.length + 1}`,
      type: 'shallow_branch',
      severity: 'warning',
      title: '主链还没有展开',
      message: '中心主题下面还没有分支，建议先拆出研究问题、方法、论据或结论。',
      node_texts: [root.text],
    })
  }

  const normalized = new Map<string, string[]>()
  for (const [id, node] of Object.entries(map.nodes)) {
    const key = node.text.trim().toLowerCase().replace(/\s+/g, '')
    if (!key || GENERIC.has(key)) continue
    normalized.set(key, [...(normalized.get(key) ?? []), id])
  }
  for (const [text, ids] of normalized) {
    if (ids.length > 1) {
      issues.push({
        id: `issue-${issues.length + 1}`,
        type: 'duplicate',
        severity: 'warning',
        title: '存在相似表达',
        message: `有 ${ids.length} 个节点使用了相近表述，建议合并或区分论点侧重点。`,
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
        title: '发现孤立节点',
        message: '这个节点没有有效父节点，建议把它接回主链或删除。',
        node_texts: [node.text],
      })
    }
    if (!node.children.length && (node.text.trim().length < 6 || GENERIC.has(node.text.trim()))) {
      issues.push({
        id: `issue-${issues.length + 1}`,
        type: 'missing_support',
        severity: 'info',
        title: '建议补充支撑信息',
        message: '节点内容较短，建议补充前置条件、证据来源或预期结论。',
        node_texts: [node.text],
      })
    }
  }

  return issues.slice(0, 12)
}
