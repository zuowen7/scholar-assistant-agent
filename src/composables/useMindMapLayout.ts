import dagre from 'dagre'
import { useMindMap } from './useMindMap'

const NODE_W = 196
const NODE_H = 62

export function useMindMapLayout() {
  const { draftMindMap, commitNodePositions } = useMindMap()

  function autoLayout(direction: 'LR' | 'TB' | 'radial' = 'radial') {
    const map = draftMindMap.value
    if (direction === 'radial') {
      const rootId = map.rootId
      const root = map.nodes[rootId]
      if (!root) return
      const positions: Record<string, { x: number; y: number }> = {
        [rootId]: { x: -NODE_W / 2, y: -NODE_H / 2 },
      }

      const childrenByParent = new Map<string, string[]>()
      for (const node of Object.values(map.nodes)) {
        if (!node.parentId) continue
        const siblings = childrenByParent.get(node.parentId) ?? []
        siblings.push(node.id)
        childrenByParent.set(node.parentId, siblings)
      }

      const rootChildren = childrenByParent.get(rootId) ?? []
      const sides = {
        left: rootChildren.filter((_, index) => index % 2 === 0),
        right: rootChildren.filter((_, index) => index % 2 === 1),
      }

      const spanCache = new Map<string, number>()
      const subtreeSpan = (nodeId: string): number => {
        const cached = spanCache.get(nodeId)
        if (cached !== undefined) return cached
        const children = childrenByParent.get(nodeId) ?? []
        const span = Math.max(1, children.reduce((total, childId) => total + subtreeSpan(childId), 0))
        spanCache.set(nodeId, span)
        return span
      }

      const leafGap = 112
      const rootGap = 286
      const depthGap = 252
      const placeBranch = (nodeId: string, side: -1 | 1, depth: number, startSlot: number, offsetY: number) => {
        const span = subtreeSpan(nodeId)
        const centerSlot = startSlot + (span - 1) / 2
        positions[nodeId] = {
          x: side * (rootGap + (depth - 1) * depthGap) - NODE_W / 2,
          y: offsetY + centerSlot * leafGap - NODE_H / 2,
        }
        let childSlot = startSlot
        for (const childId of childrenByParent.get(nodeId) ?? []) {
          placeBranch(childId, side, depth + 1, childSlot, offsetY)
          childSlot += subtreeSpan(childId)
        }
      }

      const placeSide = (ids: string[], side: -1 | 1) => {
        const totalSpan = ids.reduce((total, id) => total + subtreeSpan(id), 0)
        const offsetY = -((totalSpan - 1) * leafGap) / 2
        let startSlot = 0
        for (const id of ids) {
          placeBranch(id, side, 1, startSlot, offsetY)
          startSlot += subtreeSpan(id)
        }
      }
      placeSide(sides.left, -1)
      placeSide(sides.right, 1)
      commitNodePositions(positions)
      return
    }

    const g = new dagre.graphlib.Graph()
    g.setGraph({ rankdir: direction, nodesep: 30, ranksep: 80 })
    g.setDefaultEdgeLabel(() => ({}))

    for (const id of Object.keys(map.nodes)) {
      g.setNode(id, { width: NODE_W, height: NODE_H })
    }
    for (const node of Object.values(map.nodes)) {
      if (node.parentId) g.setEdge(node.parentId, node.id)
    }

    dagre.layout(g)

    const positions: Record<string, { x: number; y: number }> = {}
    for (const id of Object.keys(map.nodes)) {
      const pos = g.node(id)
      if (pos) {
        positions[id] = { x: pos.x - NODE_W / 2, y: pos.y - NODE_H / 2 }
      }
    }
    commitNodePositions(positions)
  }

  return { autoLayout }
}
