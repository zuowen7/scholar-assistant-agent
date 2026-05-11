/**
 * Phase 2 TDD — useArgumentMap composable unit tests.
 *
 * Tests pure functions (toFlowNodes, toFlowEdges, inferRelationType)
 * and undo/redo behavior with mocked fetch.
 */
import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'

vi.mock('../utils/api', () => ({ API_BASE: 'http://127.0.0.1:18088' }))

import {
  toFlowNodes,
  toFlowEdges,
  inferRelationType,
  useArgumentMap,
  _resetForTesting,
} from '../composables/useArgumentMap'
import type { ArgNode, ArgEdge, ArgGraph, NodeType, RelationType } from '../composables/useArgumentMap'

let _nodeCounter = 0
let _edgeCounter = 0

function makeNode(partial: Partial<ArgNode> = {}): ArgNode {
  _nodeCounter++
  return {
    id: `n_${_nodeCounter}`,
    node_type: 'claim',
    text: 'Test node',
    issue_ids: [],
    span_ids: [],
    created_by: 'user',
    position: null,
    ...partial,
  }
}

function makeEdge(partial: Partial<ArgEdge> = {}): ArgEdge {
  _edgeCounter++
  return {
    id: `e_${_edgeCounter}`,
    source_id: 'n_src',
    target_id: 'n_tgt',
    relation_type: 'supports',
    created_by: 'user',
    ...partial,
  }
}

function makeGraph(partial: Partial<ArgGraph> = {}): ArgGraph {
  return {
    id: 'g_test',
    title: 'Test Graph',
    nodes: [],
    edges: [],
    spans: [],
    issues: [],
    created_at: 0,
    updated_at: 0,
    ...partial,
  }
}

// ── toFlowNodes ───────────────────────────────────────────────────────────────

describe('toFlowNodes', () => {
  it('converts ArgNode to Vue Flow node format', () => {
    const node = makeNode({ id: 'n_a', node_type: 'claim', text: 'Main claim', position: { x: 100, y: 200 } })
    const graph = makeGraph({ nodes: [node] })
    const result = toFlowNodes(graph)

    expect(result).toHaveLength(1)
    expect(result[0].id).toBe('n_a')
    expect(result[0].type).toBe('argNode')
    expect(result[0].position).toEqual({ x: 100, y: 200 })
    expect(result[0].data.node_type).toBe('claim')
    expect(result[0].data.text).toBe('Main claim')
  })

  it('provides a default position when node.position is null', () => {
    const node = makeNode({ id: 'n_b', position: null })
    const result = toFlowNodes(makeGraph({ nodes: [node] }))

    expect(result[0].position).toBeDefined()
    expect(typeof result[0].position.x).toBe('number')
    expect(typeof result[0].position.y).toBe('number')
  })

  it('includes issueCount in node data', () => {
    const node = makeNode({ id: 'n_c', issue_ids: ['is_1', 'is_2', 'is_3'] })
    const result = toFlowNodes(makeGraph({ nodes: [node] }))

    expect(result[0].data.issueCount).toBe(3)
  })

  it('includes created_by in node data', () => {
    const node = makeNode({ id: 'n_d', created_by: 'ai' })
    const result = toFlowNodes(makeGraph({ nodes: [node] }))

    expect(result[0].data.created_by).toBe('ai')
  })

  it('returns empty array for a graph with no nodes', () => {
    expect(toFlowNodes(makeGraph())).toEqual([])
  })

  it('converts all six node types correctly', () => {
    const types: NodeType[] = ['claim', 'grounds', 'warrant', 'backing', 'qualifier', 'rebuttal']
    const nodes = types.map((t, i) => makeNode({ id: `n_${t}`, node_type: t }))
    const result = toFlowNodes(makeGraph({ nodes }))

    expect(result).toHaveLength(6)
    types.forEach((t, i) => {
      expect(result[i].data.node_type).toBe(t)
    })
  })

  it('uses label from node when present', () => {
    const node = makeNode({ id: 'n_e', text: 'Long text here', label: 'Short label' })
    const result = toFlowNodes(makeGraph({ nodes: [node] }))

    expect(result[0].data.label).toBe('Short label')
  })
})

// ── toFlowEdges ───────────────────────────────────────────────────────────────

describe('toFlowEdges', () => {
  it('converts ArgEdge to Vue Flow edge format', () => {
    const edge = makeEdge({ id: 'e_a', source_id: 'n_src', target_id: 'n_tgt', relation_type: 'supports' })
    const result = toFlowEdges(makeGraph({ edges: [edge] }))

    expect(result).toHaveLength(1)
    expect(result[0].id).toBe('e_a')
    expect(result[0].source).toBe('n_src')
    expect(result[0].target).toBe('n_tgt')
    expect(result[0].type).toBe('argEdge')
    expect(result[0].data.relation_type).toBe('supports')
  })

  it('sets label to relation_type', () => {
    const edge = makeEdge({ id: 'e_b', relation_type: 'rebuts' })
    const result = toFlowEdges(makeGraph({ edges: [edge] }))

    expect(result[0].label).toBe('rebuts')
  })

  it('returns empty array for a graph with no edges', () => {
    expect(toFlowEdges(makeGraph())).toEqual([])
  })

  it('converts all six relation types', () => {
    const types: RelationType[] = ['supports', 'warrants', 'backs', 'qualifies', 'rebuts', 'counters']
    const edges = types.map((r, i) =>
      makeEdge({ id: `e_${r}`, relation_type: r, source_id: `n_s${i}`, target_id: `n_t${i}` }),
    )
    const result = toFlowEdges(makeGraph({ edges }))

    expect(result).toHaveLength(6)
    types.forEach((r, i) => {
      expect(result[i].data.relation_type).toBe(r)
    })
  })

  it('includes created_by in edge data', () => {
    const edge = makeEdge({ id: 'e_c', created_by: 'ai' })
    const result = toFlowEdges(makeGraph({ edges: [edge] }))

    expect(result[0].data.created_by).toBe('ai')
  })
})

// ── inferRelationType ─────────────────────────────────────────────────────────

describe('inferRelationType', () => {
  it('infers supports for grounds → claim', () => {
    expect(inferRelationType('grounds', 'claim')).toBe('supports')
  })

  it('infers warrants for warrant → claim', () => {
    expect(inferRelationType('warrant', 'claim')).toBe('warrants')
  })

  it('infers backs for backing → warrant', () => {
    expect(inferRelationType('backing', 'warrant')).toBe('backs')
  })

  it('infers qualifies for qualifier → claim', () => {
    expect(inferRelationType('qualifier', 'claim')).toBe('qualifies')
  })

  it('infers rebuts for rebuttal → claim', () => {
    expect(inferRelationType('rebuttal', 'claim')).toBe('rebuts')
  })

  it('infers counters for claim → rebuttal', () => {
    expect(inferRelationType('claim', 'rebuttal')).toBe('counters')
  })

  it('infers counters for grounds → rebuttal', () => {
    expect(inferRelationType('grounds', 'rebuttal')).toBe('counters')
  })

  it('returns null for invalid combo: claim → claim', () => {
    expect(inferRelationType('claim', 'claim')).toBeNull()
  })

  it('returns null for invalid combo: grounds → grounds', () => {
    expect(inferRelationType('grounds', 'grounds')).toBeNull()
  })

  it('returns null for invalid combo: claim → grounds', () => {
    expect(inferRelationType('claim', 'grounds')).toBeNull()
  })

  it('returns null for invalid combo: backing → claim', () => {
    expect(inferRelationType('backing', 'claim')).toBeNull()
  })
})

// ── undo / redo ───────────────────────────────────────────────────────────────

describe('useArgumentMap undo/redo', () => {
  beforeEach(() => {
    _resetForTesting()
    vi.clearAllMocks()
    // Seed state with an empty graph so upsertNode has a gid to work with
    const { state } = useArgumentMap()
    state.graph = makeGraph({ id: 'g_main', nodes: [], edges: [] }) as any
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('undo reverts an upserted node', async () => {
    const { state, upsertNode, undo } = useArgumentMap()
    const node = makeNode({ id: 'n_undo1', node_type: 'claim', text: 'Undoable' })

    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => node,
    } as Response)

    await upsertNode(node as any)
    expect(state.graph!.nodes).toHaveLength(1)

    undo()
    expect(state.graph!.nodes).toHaveLength(0)
  })

  it('redo replays a reverted node upsert', async () => {
    const { state, upsertNode, undo, redo } = useArgumentMap()
    const node = makeNode({ id: 'n_redo1', node_type: 'grounds', text: 'Redoable' })

    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => node,
    } as Response)

    await upsertNode(node as any)
    undo()
    expect(state.graph!.nodes).toHaveLength(0)

    redo()
    expect(state.graph!.nodes).toHaveLength(1)
  })

  it('undo is a no-op when history is empty', () => {
    const { state, undo } = useArgumentMap()
    expect(() => undo()).not.toThrow()
    expect(state.graph!.nodes).toHaveLength(0)
  })

  it('redo is a no-op when redo stack is empty', () => {
    const { state, redo } = useArgumentMap()
    expect(() => redo()).not.toThrow()
    expect(state.graph!.nodes).toHaveLength(0)
  })

  it('upsert twice then undo twice restores empty state', async () => {
    const { state, upsertNode, undo } = useArgumentMap()

    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({}),
    } as Response)

    const n1 = makeNode({ id: 'n_a1', node_type: 'claim', text: 'First' })
    const n2 = makeNode({ id: 'n_b1', node_type: 'grounds', text: 'Second' })

    await upsertNode(n1 as any)
    await upsertNode(n2 as any)
    expect(state.graph!.nodes).toHaveLength(2)

    undo()
    expect(state.graph!.nodes).toHaveLength(1)

    undo()
    expect(state.graph!.nodes).toHaveLength(0)
  })
})
