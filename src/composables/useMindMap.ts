import { computed, ref } from 'vue'

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
    saveMindMap,
    selectNode,
    updateNodeText,
    setNodePosition,
    addChild,
    addAssociationLink,
    deleteNode,
  }
}
