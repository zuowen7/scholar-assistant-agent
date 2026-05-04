<template>
  <div class="argument-map">
    <div class="arg-toolbar">
      <input
        v-model="newTopic"
        class="arg-input"
        placeholder="论证主题"
        @keydown.enter="createTree"
      />
      <button class="arg-btn primary" :disabled="loading || !newTopic.trim()" @click="createTree">新建</button>
    </div>

    <div v-if="message" class="arg-message">{{ message }}</div>

    <div v-if="!tree" class="arg-empty">
      新建一个论证图，把想法逐步展开成论文结构。
    </div>

    <template v-else>
      <div class="arg-actions">
        <button class="arg-btn" :disabled="loading || !selectedNodeId" @click="expandSelected">AI 展开</button>
        <button class="arg-btn" :disabled="loading || !selectedNodeId" @click="reviewSelected">逻辑审查</button>
        <button class="arg-btn" :disabled="loading" @click="flattenTree">生成草稿</button>
      </div>

      <div class="arg-canvas">
        <button
          v-for="node in orderedNodes"
          :key="node.id"
          type="button"
          class="arg-node"
          :class="[node.logic_status, { selected: node.id === selectedNodeId, bound: node.references.length > 0 }]"
          :style="{ marginLeft: `${node.depth * 18}px` }"
          @click="selectNode(node.id)"
        >
          <span class="arg-node-title">{{ node.topic }}</span>
          <span class="arg-node-meta">
            {{ node.status }}
            <template v-if="node.references.length"> · {{ node.references.length }} 条引用</template>
          </span>
        </button>
      </div>

      <div v-if="selectedNode" class="arg-detail">
        <label class="arg-label">
          主题
          <input v-model="selectedDraft.topic" class="arg-input" />
        </label>
        <label class="arg-label">
          内容
          <textarea v-model="selectedDraft.content" class="arg-textarea" rows="4"></textarea>
        </label>
        <div class="arg-detail-actions">
          <button class="arg-btn primary" :disabled="loading" @click="saveSelected">保存节点</button>
          <button class="arg-btn" :disabled="loading" @click="observeSelected">查找引用</button>
        </div>
        <div v-if="selectedNode.agent_feedback" class="arg-feedback">
          {{ selectedNode.agent_feedback }}
        </div>
      </div>

      <div v-if="recommendations.length" class="arg-recs">
        <div class="arg-section-title">推荐参考文献</div>
        <div v-for="rec in recommendations" :key="rec.doc_id" class="arg-rec">
          <div>
            <strong>{{ rec.title || rec.doc_id }}</strong>
            <span>{{ Math.round(rec.relevance_score * 100) }}%</span>
          </div>
          <p>{{ rec.excerpt }}</p>
          <button class="arg-btn tiny" @click="bindReference(rec)">绑定</button>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { API_BASE } from '../utils/api'

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

function setMessage(text: string) {
  message.value = text
  window.setTimeout(() => {
    if (message.value === text) message.value = ''
  }, 3000)
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
  try {
    const data = await request<{ task_id: string }>('/api/argument/flatten', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ node_id: 'root', template: 'markdown', include_references: true }),
    })
    window.open(`${API_BASE}/api/argument/download/${data.task_id}`, '_blank')
    setMessage('草稿已生成')
  } catch (e) {
    setMessage(e instanceof Error ? e.message : String(e))
  } finally {
    loading.value = false
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
.arg-toolbar,
.arg-actions,
.arg-detail-actions {
  display: flex;
  gap: 8px;
}
.arg-input,
.arg-textarea {
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
.arg-textarea {
  resize: vertical;
  min-height: 80px;
}
.arg-btn {
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
.arg-btn.primary {
  border-color: var(--c-accent);
  background: var(--c-accent);
  color: #fff;
}
.arg-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.arg-btn.tiny {
  padding: 4px 8px;
}
.arg-empty,
.arg-message {
  color: var(--c-text-2);
  font-size: 12px;
  line-height: 1.5;
}
.arg-message {
  color: var(--c-accent);
}
.arg-canvas {
  flex: 1;
  min-height: 160px;
  overflow-y: auto;
  border: 1px solid var(--c-surface-3);
  border-radius: 8px;
  padding: 10px;
  background: var(--c-surface-1);
}
.arg-node {
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
.arg-node.selected {
  border-color: var(--c-accent);
}
.arg-node.warning {
  border-left-color: #eab308;
}
.arg-node.error {
  border-left-color: #ef4444;
}
.arg-node.pass {
  border-left-color: #22c55e;
}
.arg-node.bound {
  box-shadow: inset 0 0 0 1px rgba(99, 102, 241, 0.35);
}
.arg-node-title {
  font-size: 13px;
  font-weight: 650;
}
.arg-node-meta {
  color: var(--c-text-2);
  font-size: 11px;
}
.arg-detail,
.arg-recs {
  display: flex;
  flex-direction: column;
  gap: 8px;
  border-top: 1px solid var(--c-surface-3);
  padding-top: 10px;
}
.arg-label {
  display: flex;
  flex-direction: column;
  gap: 5px;
  color: var(--c-text-2);
  font-size: 11px;
}
.arg-feedback {
  padding: 8px 10px;
  border-radius: 7px;
  background: rgba(234, 179, 8, 0.12);
  color: var(--c-text-0);
  font-size: 12px;
  line-height: 1.5;
}
.arg-section-title {
  color: var(--c-text-2);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.arg-rec {
  padding: 8px;
  border: 1px solid var(--c-surface-3);
  border-radius: 7px;
  background: var(--c-surface-2);
}
.arg-rec div {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
}
.arg-rec p {
  margin: 5px 0 8px;
  color: var(--c-text-2);
  font-size: 11px;
  line-height: 1.5;
}
</style>
