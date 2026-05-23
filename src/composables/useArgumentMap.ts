import { reactive, ref } from 'vue'
import { API_BASE } from '../utils/api'
import { readSseStream } from '../utils/streamReader'
import type { BlockData } from '../types/index'
import { useTranslate } from './useTranslate'
import { useEditor } from './useEditor'
import { useToast } from './useToast'
import { useArgumentLayout } from './useArgumentLayout'

const { pushError } = useToast()

// ── Types ─────────────────────────────────────────────────────────────────────

export type NodeType = 'claim' | 'grounds' | 'warrant' | 'backing' | 'qualifier' | 'rebuttal'
export type RelationType = 'supports' | 'warrants' | 'backs' | 'qualifies' | 'rebuts' | 'counters'

export interface ArgNode {
  id: string
  node_type: NodeType
  text: string
  label?: string | null
  confidence?: number | null
  position?: { x: number; y: number } | null
  span_ids: string[]
  issue_ids: string[]
  created_by: 'user' | 'ai'
}

export interface ArgEdge {
  id: string
  source_id: string
  target_id: string
  relation_type: RelationType
  label?: string | null
  created_by: 'user' | 'ai'
}

export interface SpanMapping {
  id: string
  node_id: string
  source_type: 'block' | 'selection' | 'editor' | 'extracted'
  block_id?: string | null
  side: 'orig' | 'trans'
  char_start?: number | null
  char_end?: number | null
  quote: string
  source_label?: string | null
}

export interface ArgIssue {
  id: string
  node_id?: string | null
  edge_id?: string | null
  severity: 'info' | 'warning' | 'error'
  category: string
  message: string
  suggestion?: string | null
}

export interface ArgGraph {
  id: string
  title: string
  nodes: ArgNode[]
  edges: ArgEdge[]
  spans: SpanMapping[]
  issues: ArgIssue[]
  source_doc?: string | null
  created_at: number
  updated_at: number
}

export interface GraphSummary {
  id: string
  title: string
  node_count: number
  updated_at: number
  source_doc?: string | null
}

export interface SuggestCandidate {
  local_id: string
  node_type: NodeType
  text: string
  created_by: 'ai'
}

export interface SuggestResult {
  candidates: SuggestCandidate[]
  suggested_edges: Array<{ source: string; target: string; relation: string }>
}

export interface FlowNode {
  id: string
  type: 'argNode'
  position: { x: number; y: number }
  data: {
    node_type: NodeType
    text: string
    label: string | null
    issueCount: number
    created_by: 'user' | 'ai'
  }
}

export interface FlowEdge {
  id: string
  source: string
  target: string
  type: 'argEdge'
  label: string
  data: {
    relation_type: RelationType
    label: string | null
    created_by: 'user' | 'ai'
  }
}

// ── Relation inference (reverse of ALLOWED_EDGES) ─────────────────────────────

const _INFER_MAP: Record<string, RelationType> = {
  'grounds→claim': 'supports',
  'warrant→claim': 'warrants',
  'backing→warrant': 'backs',
  'qualifier→claim': 'qualifies',
  'rebuttal→claim': 'rebuts',
  'claim→rebuttal': 'counters',
  'grounds→rebuttal': 'counters',
}

export function inferRelationType(srcType: string, tgtType: string): RelationType | null {
  return _INFER_MAP[`${srcType}→${tgtType}`] ?? null
}

// ── Pure adapter functions ────────────────────────────────────────────────────

export function toFlowNodes(graph: ArgGraph): FlowNode[] {
  return graph.nodes.map(n => ({
    id: n.id,
    type: 'argNode' as const,
    position: n.position ?? { x: 0, y: 0 },
    data: {
      node_type: n.node_type,
      text: n.text,
      label: n.label ?? null,
      issueCount: n.issue_ids.length,
      created_by: n.created_by,
    },
  }))
}

export function toFlowEdges(graph: ArgGraph): FlowEdge[] {
  return graph.edges.map(e => ({
    id: e.id,
    source: e.source_id,
    target: e.target_id,
    type: 'argEdge' as const,
    label: e.relation_type,
    data: {
      relation_type: e.relation_type,
      label: e.label ?? null,
      created_by: e.created_by,
    },
  }))
}

// ── Singleton state ───────────────────────────────────────────────────────────

interface SourceState {
  mode: 'paste' | 'translation' | 'editor'
  text: string
  label: string
  side: 'orig' | 'trans'
  blocks: BlockData[]
}

interface ArgumentMapState {
  graph: ArgGraph | null
  graphList: GraphSummary[]
  selectedNodeId: string
  selectedEdgeId: string
  /** Node IDs to highlight in the graph (driven by source pane hover/click) */
  highlightNodeIds: string[]
  /** Span ID currently hovered in source pane */
  hoveredSpanId: string
  /** Source text state for ArgSourcePane */
  source: SourceState
  /** True while extract SSE is in progress */
  extracting: boolean
  /** True while critique request is in progress */
  critiquing: boolean
}

const _defaultSource = (): SourceState => ({
  mode: 'paste',
  text: '',
  label: '',
  side: 'trans',
  blocks: [],
})

const _state = reactive<ArgumentMapState>({
  graph: null,
  graphList: [],
  selectedNodeId: '',
  selectedEdgeId: '',
  highlightNodeIds: [],
  hoveredSpanId: '',
  source: _defaultSource(),
  extracting: false,
  critiquing: false,
})

const _history: ArgGraph[] = []
const _redoStack: ArgGraph[] = []
const HISTORY_LIMIT = 50

function _cloneGraph(g: ArgGraph): ArgGraph {
  return JSON.parse(JSON.stringify(g))
}

function _pushHistory() {
  if (_state.graph) {
    _history.push(_cloneGraph(_state.graph))
    if (_history.length > HISTORY_LIMIT) _history.shift()
    _redoStack.length = 0
  }
}

// ── Open-full signal (lets ArgumentMapMini tell App.vue to switch mode) ──────

export const _openFullArgMapTick = ref(0)
export function requestOpenFullArgMap() { _openFullArgMapTick.value++ }

// ── Feature flag ──────────────────────────────────────────────────────────────

export const argMapV2Enabled = ref(false)

export async function checkArgumentMapV2Flag(): Promise<void> {
  try {
    const res = await fetch(`${API_BASE}/api/config`)
    if (!res.ok) return
    const cfg = await res.json()
    argMapV2Enabled.value = Boolean(cfg?.features?.argument_map_v2)
  } catch {
    argMapV2Enabled.value = false
  }
}

export function _resetForTesting() {
  argMapV2Enabled.value = false
  _state.graph = null
  _state.graphList = []
  _state.selectedNodeId = ''
  _state.selectedEdgeId = ''
  _state.highlightNodeIds = []
  _state.hoveredSpanId = ''
  _state.extracting = false
  _state.critiquing = false
  Object.assign(_state.source, _defaultSource())
  _history.length = 0
  _redoStack.length = 0
}

// ── Undo / Redo ───────────────────────────────────────────────────────────────

function undo() {
  if (!_history.length) return
  if (_state.graph) _redoStack.push(_cloneGraph(_state.graph))
  _state.graph = _history.pop()!
}

function redo() {
  if (!_redoStack.length) return
  if (_state.graph) _history.push(_cloneGraph(_state.graph))
  _state.graph = _redoStack.pop()!
}

// ── Graph CRUD ────────────────────────────────────────────────────────────────

async function createGraph(title = '未命名论证图', source_doc?: string): Promise<ArgGraph> {
  const res = await fetch(`${API_BASE}/api/argument/graph`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, source_doc }),
  })
  const g: ArgGraph = await res.json()
  _state.graph = g
  return g
}

async function loadGraph(gid: string): Promise<ArgGraph> {
  const res = await fetch(`${API_BASE}/api/argument/graph/${gid}`)
  const g: ArgGraph = await res.json()
  _state.graph = g
  return g
}

async function listGraphs(): Promise<GraphSummary[]> {
  const res = await fetch(`${API_BASE}/api/argument/graphs`)
  const list: GraphSummary[] = await res.json()
  _state.graphList = list
  return list
}

async function deleteGraph(gid: string): Promise<void> {
  await fetch(`${API_BASE}/api/argument/graph/${gid}`, { method: 'DELETE' })
  if (_state.graph?.id === gid) _state.graph = null
}

// ── Node CRUD ─────────────────────────────────────────────────────────────────

async function upsertNode(
  node: Partial<ArgNode> & { node_type: NodeType; text: string },
): Promise<ArgNode> {
  if (!_state.graph) throw new Error('No graph loaded')
  _pushHistory()

  // Optimistic local update
  const tempId = node.id ?? `n_local_${Date.now()}`
  const existing = _state.graph.nodes.find(n => n.id === node.id)
  if (existing) {
    Object.assign(existing, node)
  } else {
    _state.graph.nodes.push({
      id: tempId,
      node_type: node.node_type,
      text: node.text,
      label: node.label ?? null,
      confidence: node.confidence ?? null,
      position: node.position ?? null,
      span_ids: node.span_ids ?? [],
      issue_ids: node.issue_ids ?? [],
      created_by: node.created_by ?? 'user',
    })
  }

  const res = await fetch(`${API_BASE}/api/argument/graph/${_state.graph.id}/node`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(node),
  })
  const updated: ArgNode = await res.json()

  // Sync server-assigned id back into local state
  const idx = _state.graph.nodes.findIndex(n => n.id === tempId || n.id === updated.id)
  if (idx !== -1) _state.graph.nodes[idx] = updated

  return updated
}

async function deleteNode(nid: string): Promise<void> {
  if (!_state.graph) return
  _pushHistory()
  _state.graph.nodes = _state.graph.nodes.filter(n => n.id !== nid)
  _state.graph.edges = _state.graph.edges.filter(e => e.source_id !== nid && e.target_id !== nid)
  _state.graph.spans = _state.graph.spans.filter(s => s.node_id !== nid)
  await fetch(`${API_BASE}/api/argument/graph/${_state.graph.id}/node/${nid}`, { method: 'DELETE' })
}

// ── Edge CRUD ─────────────────────────────────────────────────────────────────

async function upsertEdge(
  edge: Partial<ArgEdge> & { source_id: string; target_id: string; relation_type: RelationType },
): Promise<ArgEdge> {
  if (!_state.graph) throw new Error('No graph loaded')
  _pushHistory()

  const res = await fetch(`${API_BASE}/api/argument/graph/${_state.graph.id}/edge`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(edge),
  })
  if (!res.ok) {
    _history.pop()
    throw new Error(await res.text())
  }
  const updated: ArgEdge = await res.json()
  const idx = _state.graph.edges.findIndex(e => e.id === updated.id)
  if (idx !== -1) {
    _state.graph.edges[idx] = updated
  } else {
    _state.graph.edges.push(updated)
  }
  return updated
}

async function deleteEdge(eid: string): Promise<void> {
  if (!_state.graph) return
  _pushHistory()
  _state.graph.edges = _state.graph.edges.filter(e => e.id !== eid)
  await fetch(`${API_BASE}/api/argument/graph/${_state.graph.id}/edge/${eid}`, { method: 'DELETE' })
}

// ── Span CRUD ─────────────────────────────────────────────────────────────────

async function addSpan(span: Omit<SpanMapping, 'id'>): Promise<SpanMapping> {
  if (!_state.graph) throw new Error('No graph loaded')
  const res = await fetch(`${API_BASE}/api/argument/graph/${_state.graph.id}/span`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(span),
  })
  const added: SpanMapping = await res.json()
  _state.graph.spans.push(added)
  return added
}

async function deleteSpan(sid: string): Promise<void> {
  if (!_state.graph) return
  _state.graph.spans = _state.graph.spans.filter(s => s.id !== sid)
  await fetch(`${API_BASE}/api/argument/graph/${_state.graph.id}/span/${sid}`, { method: 'DELETE' })
}

// ── Phase 3: source / focus helpers ──────────────────────────────────────────

/** Highlight the given node in the source pane (empty string clears). */
export function focusNode(nodeId: string): void {
  _state.highlightNodeIds = nodeId ? [nodeId] : []
}

/** Highlight the node that owns this span. */
export function focusSpan(spanId: string): void {
  const span = _state.graph?.spans.find(s => s.id === spanId)
  if (span) _state.highlightNodeIds = [span.node_id]
}

/** Set source to pasted text. */
export function setPastedSource(text: string, label = '粘贴文本'): void {
  _state.source.mode = 'paste'
  _state.source.text = text
  _state.source.label = label
  _state.source.blocks = []
}

/** Load source from the last translation result. */
export function loadSourceFromTranslation(): void {
  const { state: ts } = useTranslate()
  const blocks = [...(ts.blocks as BlockData[])]
  _state.source.mode = 'translation'
  _state.source.blocks = blocks
  _state.source.side = 'trans'
  _state.source.label = '上次翻译结果'
  _state.source.text = blocks.map(b => b.translated || b.original).filter(Boolean).join('\n\n')
}

/** Load source from the currently active editor tab. */
export function loadSourceFromEditor(): void {
  const { activeTab } = useEditor()
  const tab = activeTab.value as { content?: string; name?: string } | null
  _state.source.mode = 'editor'
  _state.source.text = tab?.content ?? ''
  _state.source.label = tab?.name ?? '编辑器文件'
  _state.source.blocks = []
}

// ── Phase 4: AI operations ────────────────────────────────────────────────────

/**
 * Extract a Toulmin argument graph from source text via SSE.
 * Streams node/edge/span events into local state, then reloads the graph.
 */
async function extractArgument(
  text: string,
  sourcLabel?: string,
  side: 'orig' | 'trans' = 'trans',
): Promise<void> {
  if (!_state.graph) throw new Error('No graph loaded')
  _state.extracting = true

  // Clear current nodes/edges/spans for fresh extraction
  _state.graph.nodes = []
  _state.graph.edges = []
  _state.graph.spans = []

  const gid = _state.graph.id
  const abort = new AbortController()
  try {
    const res = await fetch(`${API_BASE}/api/argument/graph/${gid}/extract`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, source_label: sourcLabel, side }),
      signal: abort.signal,
    })
    if (!res.body) return

    let streamDone = false
    await readSseStream(res.body.getReader(), (eventType, data) => {
      if (!_state.graph) return
      if (eventType === 'node') {
        _state.graph.nodes.push(data as unknown as ArgNode)
      } else if (eventType === 'edge') {
        _state.graph.edges.push(data as unknown as ArgEdge)
      } else if (eventType === 'span') {
        _state.graph.spans.push(data as unknown as SpanMapping)
      } else if (eventType === 'complete' || eventType === 'error') {
        streamDone = true
      }
    }, abort.signal, () => streamDone)

    // Reload from server to confirm persisted state
    await loadGraph(gid)

    // Auto-layout after extraction
    if (_state.graph && _state.graph.nodes.length) {
      const { autoLayout } = useArgumentLayout()
      const pos = autoLayout(_state.graph.nodes as any[], _state.graph.edges as any[])
      for (const p of pos) {
        const node = _state.graph.nodes.find(n => n.id === p.id)
        if (node) node.position = p.position
      }
    }
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === 'AbortError') return
    pushError(`提取论证失败：${err instanceof Error ? err.message : String(err)}`)
  } finally {
    abort.abort()
    _state.extracting = false
  }
}

/**
 * Run structural + LLM critique of the current graph.
 * Issues are written to the graph by the backend and stored in the refreshed graph.
 */
async function critiqueGraph(): Promise<ArgIssue[]> {
  if (!_state.graph) return []
  _state.critiquing = true
  try {
    const res = await fetch(
      `${API_BASE}/api/argument/graph/${_state.graph.id}/critique`,
      { method: 'POST', headers: { 'Content-Type': 'application/json' } },
    )
    if (!res.ok) return []
    const body = await res.json() as { issues: ArgIssue[] }
    // Update issue_ids on local nodes
    if (_state.graph) {
      for (const node of _state.graph.nodes) node.issue_ids = []
      for (const issue of body.issues) {
        if (issue.node_id) {
          const node = _state.graph.nodes.find(n => n.id === issue.node_id)
          if (node && !node.issue_ids.includes(issue.id)) node.issue_ids.push(issue.id)
        }
      }
      _state.graph.issues = body.issues
    }
    return body.issues
  } finally {
    _state.critiquing = false
  }
}

/**
 * Suggest next Toulmin elements for a given node.
 * Does NOT save to store — frontend shows candidates for user to accept.
 */
async function suggestElement(nodeId: string): Promise<SuggestResult> {
  if (!_state.graph) return { candidates: [], suggested_edges: [] }
  const res = await fetch(
    `${API_BASE}/api/argument/graph/${_state.graph.id}/suggest`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ node_id: nodeId }),
    },
  )
  if (!res.ok) return { candidates: [], suggested_edges: [] }
  return res.json() as Promise<SuggestResult>
}

// ── Composable (singleton) ────────────────────────────────────────────────────

export function useArgumentMap() {
  return {
    state: _state,
    // Pure adapters
    toFlowNodes: () => (_state.graph ? toFlowNodes(_state.graph) : []),
    toFlowEdges: () => (_state.graph ? toFlowEdges(_state.graph) : []),
    // History
    undo,
    redo,
    // Graph CRUD
    createGraph,
    loadGraph,
    listGraphs,
    deleteGraph,
    // Node / edge / span CRUD
    upsertNode,
    deleteNode,
    upsertEdge,
    deleteEdge,
    addSpan,
    deleteSpan,
    // Phase 3: source / focus
    focusNode,
    focusSpan,
    setPastedSource,
    loadSourceFromTranslation,
    loadSourceFromEditor,
    // Phase 4: AI operations
    extractArgument,
    critiqueGraph,
    suggestElement,
  }
}
