import { computed, ref } from 'vue'
import { API_BASE } from '../utils/api'

export interface MindMapNode {
  id: string
  text: string
  parentId: string | null
  children: string[]
}

export interface MindMapPosition {
  x: number
  y: number
}

export interface MindMapLink {
  id: string
  from: string
  to: string
  type: 'association'
}

export interface MindMapData {
  rootId: string
  nodes: Record<string, MindMapNode>
  positions: Record<string, MindMapPosition>
  links: MindMapLink[]
  updatedAt: number
}

export interface MindMapViewport {
  pan: { x: number; y: number }
  zoom: number
  toolbar: { x: number; y: number }
}

const createDefaultMap = (): MindMapData => {
  const rootId = `mind-${Date.now()}`
  return {
    rootId,
    nodes: {
      [rootId]: {
        id: rootId,
        text: '中心主题',
        parentId: null,
        children: [],
      },
    },
    positions: {
      [rootId]: { x: 120, y: 120 },
    },
    links: [],
    updatedAt: Date.now(),
  }
}

const draftMindMap = ref<MindMapData>(createDefaultMap())
const savedMindMap = ref<MindMapData | null>(null)
const selectedNodeId = ref(draftMindMap.value.rootId)
const viewport = ref<MindMapViewport>({
  pan: { x: 80, y: 80 },
  zoom: 1,
  toolbar: { x: 24, y: 18 },
})

function cloneMap(map: MindMapData): MindMapData {
  return {
    rootId: map.rootId,
    updatedAt: map.updatedAt,
    nodes: Object.fromEntries(
      Object.entries(map.nodes).map(([id, node]) => [id, { ...node, children: [...node.children] }]),
    ),
    positions: Object.fromEntries(
      Object.entries(map.positions ?? {}).map(([id, position]) => [id, { ...position }]),
    ),
    links: (map.links ?? []).map(link => ({ ...link })),
  }
}

export function mindMapToMarkdown(map: MindMapData): string {
  const lines: string[] = []
  const visit = (id: string, depth: number) => {
    const node = map.nodes[id]
    if (!node) return
    const level = Math.min(depth + 1, 6)
    const prefix = '#'.repeat(level)
    lines.push(`${prefix} ${node.text}`)
    lines.push('')
    for (const childId of node.children) {
      visit(childId, depth + 1)
    }
  }
  visit(map.rootId, 0)
  return lines.join('\n').trim() + '\n'
}

export function markdownToMindMapNodes(md: string): { text: string; children: { text: string; children: { text: string }[] }[] } | null {
  const headingPattern = /^(#{1,6})\s+(.+)$/
  const lines = md.split('\n')
  const stack: Array<{ level: number; text: string; children: any[] }> = []

  let root: { text: string; children: any[] } | null = null

  for (const line of lines) {
    const match = headingPattern.exec(line.trim())
    if (!match) continue
    const level = match[1].length
    const text = match[2].trim()
    if (!text) continue

    const node = { level, text, children: [] as any[] }

    while (stack.length > 0 && stack[stack.length - 1].level >= level) {
      stack.pop()
    }

    if (stack.length === 0) {
      if (!root) {
        root = node
      } else {
        root.children.push(node)
      }
    } else {
      stack[stack.length - 1].children.push(node)
    }
    stack.push(node)
  }

  return root
}

export function useMindMap() {
  const selectedNode = computed(() => draftMindMap.value.nodes[selectedNodeId.value] ?? null)
  const hasSavedMindMap = computed(() => savedMindMap.value !== null)

  function resetMindMap(text = '中心主题') {
    const currentToolbar = viewport.value.toolbar
    draftMindMap.value = createDefaultMap()
    draftMindMap.value.nodes[draftMindMap.value.rootId].text = text
    selectedNodeId.value = draftMindMap.value.rootId
    viewport.value = {
      pan: { x: 80, y: 80 },
      zoom: 1,
      toolbar: currentToolbar,
    }
  }

  function loadSavedMindMap() {
    if (!savedMindMap.value) {
      resetMindMap()
      return
    }
    draftMindMap.value = cloneMap(savedMindMap.value)
    selectedNodeId.value = draftMindMap.value.rootId
  }

  function saveMindMap() {
    draftMindMap.value.updatedAt = Date.now()
    savedMindMap.value = cloneMap(draftMindMap.value)
    fetch(`${API_BASE}/api/mindmap/save`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(savedMindMap.value),
    }).catch(err => console.warn('[mindmap] 保存失败:', err))
  }

  async function loadFromBackend(): Promise<boolean> {
    try {
      const res = await fetch(`${API_BASE}/api/mindmap/load`)
      if (!res.ok) return false
      const data: MindMapData = await res.json()
      savedMindMap.value = data
      draftMindMap.value = cloneMap(data)
      selectedNodeId.value = data.rootId
      return true
    }
    catch (err) {
      console.warn('[mindmap] 加载失败:', err)
      return false
    }
  }

  function selectNode(id: string) {
    if (draftMindMap.value.nodes[id]) selectedNodeId.value = id
  }

  function updateNodeText(id: string, text: string) {
    const node = draftMindMap.value.nodes[id]
    if (!node) return
    node.text = text.trim() || '未命名节点'
    draftMindMap.value.updatedAt = Date.now()
  }

  function setNodePosition(id: string, position: MindMapPosition) {
    if (!draftMindMap.value.nodes[id]) return
    draftMindMap.value.positions[id] = { ...position }
    draftMindMap.value.updatedAt = Date.now()
  }

  function addChild(parentId = selectedNodeId.value, position?: MindMapPosition) {
    const parent = draftMindMap.value.nodes[parentId]
    if (!parent) return
    const id = `mind-${Date.now()}-${Math.random().toString(16).slice(2, 6)}`
    draftMindMap.value.nodes[id] = {
      id,
      text: '新节点',
      parentId,
      children: [],
    }
    parent.children.push(id)
    if (position) draftMindMap.value.positions[id] = { ...position }
    selectedNodeId.value = id
    draftMindMap.value.updatedAt = Date.now()
  }

  function addAssociationLink(from: string, to: string) {
    const map = draftMindMap.value
    if (from === to || !map.nodes[from] || !map.nodes[to]) return
    const exists = map.links.some(link =>
      link.type === 'association'
      && ((link.from === from && link.to === to) || (link.from === to && link.to === from)),
    )
    if (exists) return
    map.links.push({
      id: `link-${Date.now()}-${Math.random().toString(16).slice(2, 6)}`,
      from,
      to,
      type: 'association',
    })
    map.updatedAt = Date.now()
  }

  async function expandNode(parentId: string): Promise<boolean> {
    const parent = draftMindMap.value.nodes[parentId]
    if (!parent) return false
    try {
      const res = await fetch(`${API_BASE}/api/mindmap/expand`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          node_text: parent.text,
          context: buildExpansionContext(parentId),
          max_children: 4,
        }),
      })
      if (!res.ok) return false
      const data = await res.json()
      const children: Array<{ text: string }> = data.children ?? []
      if (!children.length) return false
      const parentPos = draftMindMap.value.positions[parentId]
      children.forEach((child, i) => {
        addChild(parentId, parentPos
          ? { x: parentPos.x + 260, y: parentPos.y + (i - (children.length - 1) / 2) * 88 }
          : undefined,
        )
        const newNodeId = selectedNodeId.value
        updateNodeText(newNodeId, child.text)
      })
      selectedNodeId.value = parentId
      return true
    }
    catch {
      return false
    }
  }

  function buildExpansionContext(nodeId: string): string {
    const map = draftMindMap.value
    const lines: string[] = []
    const visit = (id: string, depth: number) => {
      const node = map.nodes[id]
      if (!node) return
      const indent = '  '.repeat(depth)
      lines.push(`${indent}- ${node.text}`)
      for (const cid of node.children) visit(cid, depth + 1)
    }
    visit(map.rootId, 0)
    const node = map.nodes[nodeId]
    return `完整导图结构：\n${lines.join('\n')}\n\n正在展开的节点：${node?.text ?? ''}`
  }

  function deleteNode(id = selectedNodeId.value) {
    const map = draftMindMap.value
    const node = map.nodes[id]
    if (!node || id === map.rootId) return

    const removeIds: string[] = []
    const collect = (nodeId: string) => {
      removeIds.push(nodeId)
      map.nodes[nodeId]?.children.forEach(collect)
    }
    collect(id)

    const parent = node.parentId ? map.nodes[node.parentId] : null
    if (parent) parent.children = parent.children.filter(childId => childId !== id)
    removeIds.forEach(nodeId => {
      delete map.nodes[nodeId]
      delete map.positions[nodeId]
    })
    map.links = map.links.filter(link => !removeIds.includes(link.from) && !removeIds.includes(link.to))
    selectedNodeId.value = parent?.id ?? map.rootId
    map.updatedAt = Date.now()
  }

  return {
    draftMindMap,
    savedMindMap,
    viewport,
    selectedNodeId,
    selectedNode,
    hasSavedMindMap,
    resetMindMap,
    loadSavedMindMap,
    loadFromBackend,
    saveMindMap,
    selectNode,
    updateNodeText,
    setNodePosition,
    addChild,
    addAssociationLink,
    expandNode,
    deleteNode,
  }
}
