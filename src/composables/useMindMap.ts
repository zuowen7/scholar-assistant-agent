import { computed, ref } from 'vue'

export interface MindMapNode {
  id: string
  text: string
  parentId: string | null
  children: string[]
}

export interface MindMapData {
  rootId: string
  nodes: Record<string, MindMapNode>
  updatedAt: number
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
    updatedAt: Date.now(),
  }
}

const draftMindMap = ref<MindMapData>(createDefaultMap())
const savedMindMap = ref<MindMapData | null>(null)
const selectedNodeId = ref(draftMindMap.value.rootId)

function cloneMap(map: MindMapData): MindMapData {
  return {
    rootId: map.rootId,
    updatedAt: map.updatedAt,
    nodes: Object.fromEntries(
      Object.entries(map.nodes).map(([id, node]) => [id, { ...node, children: [...node.children] }]),
    ),
  }
}

export function useMindMap() {
  const selectedNode = computed(() => draftMindMap.value.nodes[selectedNodeId.value] ?? null)
  const hasSavedMindMap = computed(() => savedMindMap.value !== null)

  function resetMindMap(text = '中心主题') {
    draftMindMap.value = createDefaultMap()
    draftMindMap.value.nodes[draftMindMap.value.rootId].text = text
    selectedNodeId.value = draftMindMap.value.rootId
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

  function addChild(parentId = selectedNodeId.value) {
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
    selectedNodeId.value = id
    draftMindMap.value.updatedAt = Date.now()
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
    removeIds.forEach(nodeId => delete map.nodes[nodeId])
    selectedNodeId.value = parent?.id ?? map.rootId
    map.updatedAt = Date.now()
  }

  return {
    draftMindMap,
    savedMindMap,
    selectedNodeId,
    selectedNode,
    hasSavedMindMap,
    resetMindMap,
    loadSavedMindMap,
    saveMindMap,
    selectNode,
    updateNodeText,
    addChild,
    deleteNode,
  }
}
