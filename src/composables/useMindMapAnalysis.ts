import type { MindMapData, MindMapNode } from './useMindMap'

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

export interface MindMapAnalysisInput {
  rootId: string
  nodes: Array<{
    id: string
    text: string
    parentId: string | null
    children: string[]
    depth: number
  }>
  treeEdges: Array<{ from: string; to: string }>
  associationEdges: Array<{ from: string; to: string }>
}

const GENERIC_NODE_TEXT = new Set(['中心主题', '新节点', '未命名节点'])

export function useMindMapAnalysis() {
  function buildAnalysisInput(map: MindMapData): MindMapAnalysisInput {
    const nodes: MindMapAnalysisInput['nodes'] = []
    const treeEdges: MindMapAnalysisInput['treeEdges'] = []

    const visit = (id: string, depth: number) => {
      const node = map.nodes[id]
      if (!node) return

      nodes.push({
        id,
        text: node.text,
        parentId: node.parentId,
        children: [...node.children],
        depth,
      })

      node.children.forEach((childId) => {
        treeEdges.push({ from: id, to: childId })
        visit(childId, depth + 1)
      })
    }

    visit(map.rootId, 0)

    const visited = new Set(nodes.map(node => node.id))
    Object.values(map.nodes).forEach((node) => {
      if (!visited.has(node.id)) {
        nodes.push({
          id: node.id,
          text: node.text,
          parentId: node.parentId,
          children: [...node.children],
          depth: 0,
        })
      }
    })

    return {
      rootId: map.rootId,
      nodes,
      treeEdges,
      associationEdges: map.links.map(link => ({ from: link.from, to: link.to })),
    }
  }

  async function analyzeMindMap(map: MindMapData): Promise<MindMapAnalysisIssue[]> {
    const input = buildAnalysisInput(map)
    return runMockAnalysis(input, map.nodes)
  }

  return {
    buildAnalysisInput,
    analyzeMindMap,
  }
}

function runMockAnalysis(input: MindMapAnalysisInput, nodeMap: Record<string, MindMapNode>) {
  const issues: MindMapAnalysisIssue[] = []
  const pushIssue = (issue: Omit<MindMapAnalysisIssue, 'id'>) => {
    issues.push({ ...issue, id: `issue-${issues.length + 1}` })
  }

  const root = nodeMap[input.rootId]
  if (root && root.children.length === 0) {
    pushIssue({
      type: 'shallow_branch',
      severity: 'warning',
      title: '主链还没有展开',
      message: '中心主题下面还没有分支，建议先拆出研究问题、方法、论据或结论。',
      nodeIds: [input.rootId],
    })
  }

  const normalized = new Map<string, string[]>()
  input.nodes.forEach((node) => {
    const key = normalizeText(node.text)
    if (!key) return
    normalized.set(key, [...(normalized.get(key) ?? []), node.id])
  })
  normalized.forEach((nodeIds, text) => {
    if (nodeIds.length > 1 && !GENERIC_NODE_TEXT.has(text)) {
      pushIssue({
        type: 'duplicate',
        severity: 'warning',
        title: '存在相似表达',
        message: `有 ${nodeIds.length} 个节点使用了相近表述，建议合并或区分论点侧重点。`,
        nodeIds,
      })
    }
  })

  input.nodes.forEach((node) => {
    const original = nodeMap[node.id]
    if (!original) return

    if (node.id !== input.rootId && (!node.parentId || !nodeMap[node.parentId])) {
      pushIssue({
        type: 'isolated',
        severity: 'critical',
        title: '发现孤立节点',
        message: '这个节点没有有效父节点，建议把它接回主链或删除。',
        nodeIds: [node.id],
      })
    }

    if (node.id !== input.rootId && node.depth <= 1 && original.children.length === 0) {
      pushIssue({
        type: 'shallow_branch',
        severity: 'info',
        title: '分支层级偏浅',
        message: '这个一级分支还没有展开，建议补充论据、方法步骤或结论节点。',
        nodeIds: [node.id],
      })
    }

    if (original.children.length === 0 && (node.text.trim().length < 6 || GENERIC_NODE_TEXT.has(node.text.trim()))) {
      pushIssue({
        type: 'missing_support',
        severity: 'info',
        title: '建议补充支撑信息',
        message: '节点内容较短，建议补充前置条件、证据来源或预期结论。',
        nodeIds: [node.id],
      })
    }

    if (node.parentId && nodeMap[node.parentId]) {
      const parent = nodeMap[node.parentId]
      if (looksLikeLogicJump(parent.text, node.text)) {
        pushIssue({
          type: 'logic_gap',
          severity: 'warning',
          title: '可能存在逻辑跳跃',
          message: '父节点和子节点表达关联较弱，建议补一个过渡节点或解释推理关系。',
          nodeIds: [parent.id, node.id],
        })
      }
    }
  })

  input.associationEdges.forEach((edge) => {
    const from = nodeMap[edge.from]
    const to = nodeMap[edge.to]
    if (!from || !to) return
    if (looksLikeLogicJump(from.text, to.text)) {
      pushIssue({
        type: 'weak_link',
        severity: 'info',
        title: '关联线解释不足',
        message: '这条自定义关联线连接的概念跨度较大，建议补充说明为什么二者相关。',
        nodeIds: [from.id, to.id],
      })
    }
  })

  return issues.slice(0, 12)
}

function normalizeText(text: string) {
  return text.trim().toLowerCase().replace(/\s+/g, '')
}

function looksLikeLogicJump(a: string, b: string) {
  const left = significantChars(a)
  const right = significantChars(b)
  if (left.size < 2 || right.size < 2) return false
  let overlap = 0
  left.forEach((char) => {
    if (right.has(char)) overlap += 1
  })
  return overlap === 0 && a.trim().length >= 4 && b.trim().length >= 4
}

function significantChars(text: string) {
  return new Set(
    text
      .trim()
      .toLowerCase()
      .replace(/[，。,.!?！？、\s]/g, '')
      .slice(0, 16)
      .split(''),
  )
}
