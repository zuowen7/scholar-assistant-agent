import dagre from 'dagre'

const NODE_W = 200
const NODE_H = 70

export interface LayoutNode {
  id: string
  node_type: string
  position?: { x: number; y: number } | null
  [key: string]: unknown
}

export interface LayoutEdge {
  id: string
  source_id: string
  target_id: string
  relation_type: string
}

export interface PositionedNode extends LayoutNode {
  position: { x: number; y: number }
}

export function useArgumentLayout() {
  function autoLayout(nodes: LayoutNode[], edges: LayoutEdge[]): PositionedNode[] {
    if (!nodes.length) return []

    const g = new dagre.graphlib.Graph()
    g.setGraph({ rankdir: 'TB', nodesep: 40, ranksep: 80 })
    g.setDefaultEdgeLabel(() => ({}))

    for (const n of nodes) {
      g.setNode(n.id, { width: NODE_W, height: NODE_H })
    }
    for (const e of edges) {
      g.setEdge(e.source_id, e.target_id)
    }

    dagre.layout(g)

    return nodes.map(n => {
      const pos = g.node(n.id)
      return {
        ...n,
        position: pos
          ? { x: pos.x - NODE_W / 2, y: pos.y - NODE_H / 2 }
          : { x: 0, y: 0 },
      }
    })
  }

  return { autoLayout }
}
