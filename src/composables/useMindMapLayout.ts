import dagre from 'dagre'
import { useMindMap } from './useMindMap'

const NODE_W = 196
const NODE_H = 62

export function useMindMapLayout() {
  const { draftMindMap, commitNodePosition } = useMindMap()

  function autoLayout(direction: 'LR' | 'TB' = 'LR') {
    const g = new dagre.graphlib.Graph()
    g.setGraph({ rankdir: direction, nodesep: 30, ranksep: 80 })
    g.setDefaultEdgeLabel(() => ({}))

    const map = draftMindMap.value
    for (const id of Object.keys(map.nodes)) {
      g.setNode(id, { width: NODE_W, height: NODE_H })
    }
    for (const node of Object.values(map.nodes)) {
      if (node.parentId) g.setEdge(node.parentId, node.id)
    }

    dagre.layout(g)

    for (const id of Object.keys(map.nodes)) {
      const pos = g.node(id)
      if (pos) {
        commitNodePosition(id, { x: pos.x - NODE_W / 2, y: pos.y - NODE_H / 2 })
      }
    }
  }

  return { autoLayout }
}
