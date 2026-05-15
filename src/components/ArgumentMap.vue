<template>
  <div class="argument-map">
    <ArgumentMapToolbar
      :tree="tree"
      :loading="loading"
      :selected-node-id="selectedNodeId"
      v-model="newTopic"
      :flatten-opts="flattenOpts"
      :flatten-progress="flattenProgress"
      :message="message"
      @create="createTree"
      @expand="expandSelected"
      @review="reviewSelected"
      @flatten="flattenTree"
      @update:flatten-opts="onFlattenOptsUpdate"
    />

    <template v-if="tree">
      <ArgumentMapCanvas
        :ordered-nodes="orderedNodes"
        :selected-node-id="selectedNodeId"
        @select="selectNode"
      />

      <ArgumentMapNodeEditor
        :selected-node="selectedNode"
        :selected-draft="selectedDraft"
        :loading="loading"
        :recommendations="recommendations"
        @save="saveSelected"
        @observe="observeSelected"
        @bind="bindReference"
        @update:selected-draft="onSelectedDraftUpdate"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { API_BASE } from '../utils/api'
import { readSseStream } from '../utils/streamReader'
import ArgumentMapToolbar from './ArgumentMapToolbar.vue'
import ArgumentMapCanvas from './ArgumentMapCanvas.vue'
import ArgumentMapNodeEditor from './ArgumentMapNodeEditor.vue'

interface ArgumentReference {
  doc_id: string
  citation_key: string
  relevance_score: number
  binding_type: string
  bound_at: string
}

interface ArgumentNode {
  id: string
  parent_id: string | null
  topic: string
  content: string
  depth: number
  position: { x: number; y: number }
  domain_tags: string[]
  references: ArgumentReference[]
  logic_status: 'draft' | 'pass' | 'warning' | 'error'
  rule_issues: string[]
  agent_feedback: string | null
  status: 'draft' | 'expanded' | 'final'
  children: string[]
}

interface ArgumentTree {
  root_id: string
  nodes: Record<string, ArgumentNode>
  created_at: string
  updated_at: string
}

interface Recommendation {
  doc_id: string
  title: string
  relevance_score: number
  excerpt: string
}

const tree = ref<ArgumentTree | null>(null)
const selectedNodeId = ref('')
const newTopic = ref('')
const loading = ref(false)
const message = ref('')
const recommendations = ref<Recommendation[]>([])
const selectedDraft = reactive({ topic: '', content: '' })

const flattenOpts = reactive({
  template: 'markdown' as 'markdown' | 'latex' | 'docx',
  latex_template: 'generic_article',
  include_references: true,
})

const flattenProgress = reactive({
  active: false,
  pct: 0,
  text: '',
  total: 0,
  done: 0,
})

const selectedNode = computed(() => selectedNodeId.value && tree.value ? tree.value.nodes[selectedNodeId.value] : null)
const orderedNodes = computed(() => {
  if (!tree.value) return []
  const nodes = tree.value.nodes
  const output: ArgumentNode[] = []
  const visit = (id: string) => {
    const node = nodes[id]
    if (!node) return
    output.push(node)
    node.children.forEach(visit)
  }
  visit(tree.value.root_id)
  return output
})

function onFlattenOptsUpdate(val: { template: string; latex_template: string; include_references: boolean }) {
  flattenOpts.template = val.template as 'markdown' | 'latex' | 'docx'
  flattenOpts.latex_template = val.latex_template
  flattenOpts.include_references = val.include_references
}

function onSelectedDraftUpdate(val: { topic: string; content: string }) {
  selectedDraft.topic = val.topic
  selectedDraft.content = val.content
}

function setMessage(text: string) {
  message.value = text
  window.setTimeout(() => {
    if (message.value === text) message.value = ''
  }, 4000)
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, init)
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  return await resp.json() as T
}

async function loadTree() {
  try {
    tree.value = await request<ArgumentTree>('/api/argument/tree')
    if (!selectedNodeId.value) selectNode(tree.value.root_id)
  } catch {
    tree.value = null
  }
}

async function createTree() {
  if (!newTopic.value.trim()) return
  loading.value = true
  try {
    tree.value = await request<ArgumentTree>('/api/argument/tree', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ topic: newTopic.value.trim(), domain_tags: [] }),
    })
    selectNode(tree.value.root_id)
    setMessage('论证图已创建')
  } catch (e) {
    setMessage(e instanceof Error ? e.message : String(e))
  } finally {
    loading.value = false
  }
}

function selectNode(id: string) {
  selectedNodeId.value = id
  recommendations.value = []
  const node = tree.value?.nodes[id]
  selectedDraft.topic = node?.topic || ''
  selectedDraft.content = node?.content || ''
}

async function saveSelected() {
  const node = selectedNode.value
  if (!node) return
  loading.value = true
  try {
    await request<ArgumentNode>('/api/argument/node', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: node.id,
        parent_id: node.parent_id,
        topic: selectedDraft.topic,
        content: selectedDraft.content,
        domain_tags: node.domain_tags,
        position: node.position,
      }),
    })
    await loadTree()
    setMessage('节点已保存')
  } catch (e) {
    setMessage(e instanceof Error ? e.message : String(e))
  } finally {
    loading.value = false
  }
}

async function expandSelected() {
  if (!selectedNodeId.value) return
  loading.value = true
  try {
    await request('/api/argument/expand', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ node_id: selectedNodeId.value, max_children: 4 }),
    })
    await loadTree()
    setMessage('节点已展开')
  } catch (e) {
    setMessage(e instanceof Error ? e.message : String(e))
  } finally {
    loading.value = false
  }
}

async function reviewSelected() {
  if (!selectedNodeId.value) return
  loading.value = true
  try {
    await request('/api/argument/review', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ node_id: selectedNodeId.value, include_subtree: true }),
    })
    await loadTree()
    setMessage('逻辑审查完成')
  } catch (e) {
    setMessage(e instanceof Error ? e.message : String(e))
  } finally {
    loading.value = false
  }
}

async function observeSelected() {
  if (!selectedNodeId.value) return
  loading.value = true
  try {
    const data = await request<{ recommendations: Recommendation[] }>('/api/argument/observe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ node_id: selectedNodeId.value, content_hint: selectedDraft.content }),
    })
    recommendations.value = data.recommendations
    setMessage(data.recommendations.length ? `找到 ${data.recommendations.length} 条参考文献` : '没有匹配到强相关参考文献')
  } catch (e) {
    setMessage(e instanceof Error ? e.message : String(e))
  } finally {
    loading.value = false
  }
}

async function bindReference(rec: Recommendation) {
  if (!selectedNodeId.value) return
  await request('/api/argument/bind', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      node_id: selectedNodeId.value,
      doc_id: rec.doc_id,
      relevance_score: rec.relevance_score,
      binding_type: 'user_manual',
    }),
  })
  await loadTree()
  setMessage('参考文献已绑定')
}

async function flattenTree() {
  loading.value = true
  flattenProgress.active = true
  flattenProgress.pct = 0
  flattenProgress.done = 0
  flattenProgress.total = orderedNodes.value.length || 1
  flattenProgress.text = '正在启动降维展开…'

  try {
    // Step 1: POST to start the task
    const data = await request<{ task_id: string }>('/api/argument/flatten', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        node_id: 'root',
        template: flattenOpts.template,
        include_references: flattenOpts.include_references,
        latex_template: flattenOpts.latex_template,
      }),
    })

    // Step 2: Open SSE stream to track progress
    const sseResp = await fetch(`${API_BASE}/api/argument/flatten/${data.task_id}`)
    if (sseResp.body) {
      const reader = sseResp.body.getReader()
      await readSseStream(reader, (eventType, eventData) => {
        const d = eventData as Record<string, unknown>
        if (eventType === 'node_processing') {
          flattenProgress.text = `正在扩写节点…`
        } else if (eventType === 'node_complete') {
          flattenProgress.done++
          flattenProgress.pct = Math.round((flattenProgress.done / flattenProgress.total) * 70)
          flattenProgress.text = `扩写中 ${flattenProgress.done}/${flattenProgress.total}`
        } else if (eventType === 'polish_start') {
          flattenProgress.pct = 75
          flattenProgress.text = '正在生成摘要与过渡…'
        } else if (eventType === 'reference_processing') {
          flattenProgress.pct = 85
          flattenProgress.text = '正在处理参考文献…'
        } else if (eventType === 'complete') {
          flattenProgress.pct = 100
          flattenProgress.text = '完成!'
          const outputPath = d.output_path as string
          if (outputPath) {
            // Download the generated file
            window.open(`${API_BASE}/api/argument/download/${data.task_id}`, '_blank')
          }
        }
      })
    }

    setMessage('草稿生成完成')
  } catch (e) {
    setMessage(e instanceof Error ? e.message : String(e))
  } finally {
    loading.value = false
    window.setTimeout(() => {
      flattenProgress.active = false
    }, 1500)
  }
}

onMounted(loadTree)
</script>

<style scoped>
.argument-map {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px;
  overflow: hidden;
}

/* ── ArgumentMapToolbar :deep() ── */
.argument-map :deep(.arg-toolbar),
.argument-map :deep(.arg-actions),
.argument-map :deep(.arg-detail-actions) {
  display: flex;
  gap: 8px;
}
.argument-map :deep(.arg-export-opts) {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.argument-map :deep(.arg-label-inline) {
  display: flex;
  align-items: center;
  gap: 5px;
  color: var(--c-text-2);
  font-size: 11px;
  cursor: pointer;
}
.argument-map :deep(.arg-select) {
  border: 1px solid var(--c-surface-3);
  border-radius: 6px;
  background: var(--c-surface-2);
  color: var(--c-text-0);
  padding: 4px 6px;
  font: inherit;
  font-size: 11px;
  outline: none;
  cursor: pointer;
}
.argument-map :deep(.arg-progress) {
  display: flex;
  align-items: center;
  gap: 8px;
}
.argument-map :deep(.arg-progress-bar) {
  flex: 1;
  height: 6px;
  border-radius: 3px;
  background: var(--c-surface-3);
  overflow: hidden;
}
.argument-map :deep(.arg-progress-fill) {
  height: 100%;
  border-radius: 3px;
  background: var(--c-accent);
  transition: width 0.3s ease;
}
.argument-map :deep(.arg-progress-text) {
  font-size: 11px;
  color: var(--c-text-2);
  white-space: nowrap;
  min-width: 100px;
}
.argument-map :deep(.arg-input),
.argument-map :deep(.arg-textarea) {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid var(--c-surface-3);
  border-radius: 7px;
  background: var(--input-bg);
  color: var(--c-text-0);
  padding: 8px 10px;
  font: inherit;
  font-size: 12px;
  outline: none;
}
.argument-map :deep(.arg-textarea) {
  resize: vertical;
  min-height: 80px;
}
.argument-map :deep(.arg-btn) {
  border: 1px solid var(--c-surface-3);
  border-radius: 7px;
  background: var(--c-surface-2);
  color: var(--c-text-0);
  padding: 7px 10px;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
}
.argument-map :deep(.arg-btn.primary) {
  border-color: var(--c-accent);
  background: var(--c-accent);
  color: #fff;
}
.argument-map :deep(.arg-btn:disabled) {
  opacity: 0.5;
  cursor: not-allowed;
}
.argument-map :deep(.arg-btn.tiny) {
  padding: 4px 8px;
}
.argument-map :deep(.arg-empty),
.argument-map :deep(.arg-message) {
  color: var(--c-text-2);
  font-size: 12px;
  line-height: 1.5;
}
.argument-map :deep(.arg-message) {
  color: var(--c-accent);
}

/* ── ArgumentMapCanvas :deep() ── */
.argument-map :deep(.arg-canvas) {
  flex: 1;
  min-height: 160px;
  overflow-y: auto;
  border: 1px solid var(--c-surface-3);
  border-radius: 8px;
  padding: 10px;
  background: var(--c-surface-1);
}
.argument-map :deep(.arg-node) {
  width: calc(100% - 4px);
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin: 0 0 8px;
  padding: 9px 10px;
  border: 1px solid var(--c-surface-3);
  border-left-width: 3px;
  border-radius: 8px;
  background: var(--c-surface-2);
  color: var(--c-text-0);
  text-align: left;
  cursor: pointer;
}
.argument-map :deep(.arg-node.selected) {
  border-color: var(--c-accent);
}
.argument-map :deep(.arg-node.warning) {
  border-left-color: #eab308;
}
.argument-map :deep(.arg-node.error) {
  border-left-color: #ef4444;
}
.argument-map :deep(.arg-node.pass) {
  border-left-color: #22c55e;
}
.argument-map :deep(.arg-node.bound) {
  box-shadow: inset 0 0 0 1px rgba(99, 102, 241, 0.35);
}
.argument-map :deep(.arg-node-title) {
  font-size: 13px;
  font-weight: 650;
}
.argument-map :deep(.arg-node-meta) {
  color: var(--c-text-2);
  font-size: 11px;
}

/* ── ArgumentMapNodeEditor :deep() ── */
.argument-map :deep(.arg-detail),
.argument-map :deep(.arg-recs) {
  display: flex;
  flex-direction: column;
  gap: 8px;
  border-top: 1px solid var(--c-surface-3);
  padding-top: 10px;
}
.argument-map :deep(.arg-label) {
  display: flex;
  flex-direction: column;
  gap: 5px;
  color: var(--c-text-2);
  font-size: 11px;
}
.argument-map :deep(.arg-feedback) {
  padding: 8px 10px;
  border-radius: 7px;
  background: rgba(234, 179, 8, 0.12);
  color: var(--c-text-0);
  font-size: 12px;
  line-height: 1.5;
}
.argument-map :deep(.arg-section-title) {
  color: var(--c-text-2);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.argument-map :deep(.arg-rec) {
  padding: 8px;
  border: 1px solid var(--c-surface-3);
  border-radius: 7px;
  background: var(--c-surface-2);
}
.argument-map :deep(.arg-rec div) {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
}
.argument-map :deep(.arg-rec p) {
  margin: 5px 0 8px;
  color: var(--c-text-2);
  font-size: 11px;
  line-height: 1.5;
}
</style>
