import dagre from 'dagre'

const NODE_W_MIN = 150
const NODE_W_MAX = 260
const NODE_H_MIN = 56
const NODE_H_MAX = 140
const CHAR_W = 7.2
const CHARS_PER_LINE = 26
const LINE_H = 18
const H_PAD = 36

function nodeSize(text: string | undefined): { width: number; height: number } {
  const len = text?.length ?? 20
  const w = Math.round(Math.min(Math.max(len * CHAR_W, NODE_W_MIN), NODE_W_MAX))
  const lines = Math.max(Math.ceil(len / CHARS_PER_LINE), 1)
  const h = Math.round(Math.min(Math.max(lines * LINE_H + H_PAD, NODE_H_MIN), NODE_H_MAX))
  return { width: w, height: h }
}

/** Edge minlen — controls vertical spacing between Toulmin layers. */
const RELATION_MINLEN: Record<string, number> = {
  supports: 1,
  warrants: 2,
  backs: 2,
  qualifies: 1,
  rebuts: 2,
  counters: 2,
}

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
  function autoLayout(
    nodes: LayoutNode[],
    edges: LayoutEdge[],
    direction: 'TB' | 'LR' = 'TB',
  ): PositionedNode[] {
    if (!nodes.length) return []

    const connectedIds = new Set(edges.flatMap((edge) => [edge.source_id, edge.target_id]))
    const connectedNodes = nodes.filter((node) => connectedIds.has(node.id))
    const isolatedNodes = nodes.filter((node) => !connectedIds.has(node.id))

    if (!connectedNodes.length) {
      return nodes.map((node, index) => ({
        ...node,
        position: {
          x: (index % 3) * (NODE_W_MAX + 34),
          y: Math.floor(index / 3) * (NODE_H_MAX + 34),
        },
      }))
    }

    const g = new dagre.graphlib.Graph()
    g.setGraph({
      rankdir: direction,
      nodesep: 28,
      ranksep: 55,
      ranker: 'network-simplex',
    })
    g.setDefaultEdgeLabel(() => ({}))

    for (const n of connectedNodes) {
      const size = nodeSize(n.text as string | undefined)
      g.setNode(n.id, { width: size.width, height: size.height })
    }
    for (const e of edges) {
      const minlen = RELATION_MINLEN[e.relation_type] ?? 1
      g.setEdge(e.source_id, e.target_id, { minlen })
    }

    dagre.layout(g)

    const connectedLayout = connectedNodes.map((n) => {
      const pos = g.node(n.id)
      const size = nodeSize(n.text as string | undefined)
      return {
        ...n,
        position: pos ? { x: pos.x - size.width / 2, y: pos.y - size.height / 2 } : { x: 0, y: 0 },
      }
    })

    const xs = connectedLayout.map((node) => node.position.x)
    const ys = connectedLayout.map((node) => node.position.y)
    const minX = Math.min(...xs)
    const maxY = Math.max(...ys)
    const isolatedLayout = isolatedNodes.map((node, index) => ({
      ...node,
      position: {
        x: minX + (index % 3) * (NODE_W_MAX + 34),
        y: maxY + NODE_H_MAX + 54 + Math.floor(index / 3) * (NODE_H_MAX + 34),
      },
    }))

    const byId = new Map([...connectedLayout, ...isolatedLayout].map((node) => [node.id, node]))
    return nodes.map((node) => byId.get(node.id)!)
  }

  return { autoLayout }
}
