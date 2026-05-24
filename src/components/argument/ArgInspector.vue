<template>
  <div class="arg-inspector">
    <!-- No selection: graph stats + actions -->
    <template v-if="!selectedNode && !selectedEdge">
      <div class="inspector-section">
        <p class="inspector-title">论证图</p>
        <p v-if="state.graph" class="inspector-graph-title">{{ state.graph.title }}</p>
        <div v-if="state.graph" class="inspector-stats">
          <span class="stat-item" v-for="(count, type) in nodeTypeCounts" :key="type">
            <span class="stat-type">{{ typeLabel(type as any) }}</span>
            <span class="stat-count">{{ count }}</span>
          </span>
        </div>
        <div v-if="state.graph?.issues?.length" class="inspector-issues-count">
          ⚠ {{ state.graph.issues.length }} 个问题
        </div>
      </div>

      <!-- All graph issues -->
      <div v-if="state.graph?.issues?.length" class="inspector-field">
        <label class="inspector-label">问题清单 ({{ state.graph.issues.length }})</label>
        <div
          v-for="issue in state.graph.issues"
          :key="issue.id"
          class="inspector-issue"
          :class="`sev-${issue.severity}`"
        >
          <span class="issue-sev">{{ sevLabel(issue.severity) }}</span>
          <span class="issue-msg">{{ issue.message }}</span>
          <p v-if="issue.suggestion" class="issue-sug">{{ issue.suggestion }}</p>
        </div>
      </div>

      <!-- Export template selector -->
      <div v-if="state.graph" class="inspector-field">
        <label class="inspector-label">导出格式</label>
        <select v-model="exportTemplate" class="inspector-select">
          <option value="markdown">Markdown (.md)</option>
          <option value="latex">LaTeX (.tex)</option>
        </select>
      </div>

      <div class="inspector-actions">
        <button
          class="inspector-btn inspector-btn--primary"
          :disabled="!state.graph || state.critiquing"
          @click="doCritique"
        >{{ state.critiquing ? '审查中…' : '批判审查' }}</button>
        <button
          class="inspector-btn"
          :disabled="!state.graph || exporting"
          @click="doExport"
        >{{ exporting ? '生成中…' : '导出草稿' }}</button>
        <button class="inspector-btn" @click="$emit('auto-layout')">自动布局</button>
      </div>

      <!-- Export status -->
      <div v-if="exportMsg" class="export-msg" :class="{ 'export-msg--ok': exportOk }">
        {{ exportMsg }}
      </div>
    </template>

    <!-- Node selected -->
    <template v-else-if="selectedNode">
      <div class="inspector-section">
        <div class="inspector-node-type-badge" :class="`type-${selectedNode.node_type}`">
          {{ typeLabel(selectedNode.node_type) }}
        </div>

        <div class="inspector-field">
          <label class="inspector-label">内容</label>
          <textarea
            v-model="editText"
            class="inspector-textarea"
            rows="4"
            @blur="commitText"
          />
        </div>

        <div v-if="selectedNode.issue_ids?.length" class="inspector-field">
          <label class="inspector-label">问题 ({{ selectedNode.issue_ids.length }})</label>
          <div
            v-for="issue in nodeIssues"
            :key="issue.id"
            class="inspector-issue"
            :class="`sev-${issue.severity}`"
          >
            <span class="issue-sev">{{ sevLabel(issue.severity) }}</span>
            <span class="issue-msg">{{ issue.message }}</span>
            <p v-if="issue.suggestion" class="issue-sug">{{ issue.suggestion }}</p>
          </div>
        </div>

        <!-- Span list -->
        <div v-if="selectedNode" class="inspector-field">
          <label class="inspector-label">原文引用 ({{ nodeSpans.length }})</label>
          <div v-if="!nodeSpans.length" class="placeholder-text">从原文面板选句绑定</div>
          <div
            v-for="span in nodeSpans"
            :key="span.id"
            class="inspector-span"
          >
            <span class="span-quote">「{{ span.quote.slice(0, 36) }}{{ span.quote.length > 36 ? '…' : '' }}」</span>
            <div class="span-actions">
              <button class="span-action-btn" :title="span.source_label || span.side" @click="jumpToSpan(span.id)">跳到原文</button>
              <button class="span-action-btn span-action-btn--danger" @click="removeSpan(span.id)">解绑</button>
            </div>
          </div>
        </div>

        <!-- Suggest candidates -->
        <div v-if="suggestResult" class="inspector-field">
          <label class="inspector-label">AI 建议 ({{ suggestResult.candidates.length }})</label>
          <div
            v-for="c in suggestResult.candidates"
            :key="c.local_id"
            class="suggest-candidate"
          >
            <div class="candidate-type" :class="`type-${c.node_type}`">{{ typeLabel(c.node_type) }}</div>
            <div class="candidate-text">{{ c.text }}</div>
            <button class="candidate-adopt-btn" @click="adoptCandidate(c)">采纳</button>
          </div>
          <button class="inspector-btn" style="font-size:11px; margin-top: 4px" @click="suggestResult = null">收起</button>
        </div>
      </div>

      <div class="inspector-actions">
        <button
          class="inspector-btn"
          :disabled="!selectedNode || suggesting"
          @click="doSuggest"
        >{{ suggesting ? '建议中…' : '建议下一个元素' }}</button>
        <button class="inspector-btn inspector-btn--danger" @click="deleteSelectedNode">删除节点</button>
      </div>
    </template>

    <!-- Edge selected -->
    <template v-else-if="selectedEdge">
      <div class="inspector-section">
        <p class="inspector-title">关系</p>
        <div class="inspector-edge-rel" :class="`rel-${selectedEdge.relation_type}`">
          {{ relLabel(selectedEdge.relation_type) }}
        </div>
        <p class="inspector-edge-info">
          {{ nodeText(selectedEdge.source_id) }} →
          {{ nodeText(selectedEdge.target_id) }}
        </p>
      </div>

      <div class="inspector-actions">
        <button class="inspector-btn inspector-btn--danger" @click="deleteSelectedEdge">删除关系</button>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { NodeType, RelationType, SuggestCandidate, SuggestResult } from '../../composables/useArgumentMap'
import { useArgumentMap, focusSpan, inferRelationType } from '../../composables/useArgumentMap'
import { API_BASE } from '../../utils/api'
import { readSseStream } from '../../utils/streamReader'

defineEmits<{ 'auto-layout': [] }>()

const { state, upsertNode, deleteNode, deleteEdge, deleteSpan, critiqueGraph, suggestElement, upsertEdge } = useArgumentMap()

// ── Critique ──────────────────────────────────────────────────────────────────

async function doCritique() {
  await critiqueGraph()
}

// ── Export draft ──────────────────────────────────────────────────────────────

const exportTemplate = ref<'markdown' | 'latex'>('markdown')
const exporting = ref(false)
const exportMsg = ref('')
const exportOk = ref(false)

async function doExport() {
  if (!state.graph) return
  exporting.value = true
  exportMsg.value = '生成中…'
  exportOk.value = false

  let capturedTaskId = ''
  let capturedWordCount = 0

  try {
    const res = await fetch(`${API_BASE}/api/argument/graph/${state.graph.id}/flatten`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ template: exportTemplate.value, title: state.graph.title }),
    })
    if (!res.body) { exportMsg.value = '请求失败'; return }

    await readSseStream(res.body.getReader(), (eventType, data) => {
      if (eventType === 'complete') {
        const d = data as { output_path?: string; word_count?: number; task_id?: string }
        exportOk.value = true
        capturedTaskId = d.task_id ?? ''
        capturedWordCount = d.word_count ?? 0
        exportMsg.value = `草稿已生成（${capturedWordCount} 字），下载中…`
      } else if (eventType === 'error') {
        exportMsg.value = '导出失败：' + String((data as { message?: string }).message ?? '')
      }
    })

    if (capturedTaskId) {
      const dlResp = await fetch(`${API_BASE}/api/argument/flatten_v2/${capturedTaskId}/download`)
      if (dlResp.ok) {
        const blob = await dlResp.blob()
        const ext = exportTemplate.value === 'latex' ? 'tex' : 'md'
        const { saveBlob } = await import('../../composables/useEditorIO')
        await saveBlob(blob, `argument_draft.${ext}`)
        exportMsg.value = `草稿已导出（${capturedWordCount} 字）`
      } else {
        exportMsg.value = '文件下载失败，请重试'
      }
    }
  } catch (e) {
    exportMsg.value = '导出失败'
  } finally {
    exporting.value = false
  }
}

// ── Suggest ───────────────────────────────────────────────────────────────────

const suggesting = ref(false)
const suggestResult = ref<SuggestResult | null>(null)

async function doSuggest() {
  if (!selectedNode.value) return
  suggesting.value = true
  try {
    suggestResult.value = await suggestElement(selectedNode.value.id)
  } finally {
    suggesting.value = false
  }
}

async function adoptCandidate(c: SuggestCandidate) {
  // Position near the selected node with a small offset
  const selPos = selectedNode.value?.position
  const pos = selPos ? { x: selPos.x + 220, y: selPos.y + 40 } : { x: 100, y: 100 }
  const adopted = await upsertNode({
    node_type: c.node_type,
    text: c.text,
    created_by: 'ai',
    position: pos,
  })
  // Create edges from suggested_edges that reference this candidate
  if (suggestResult.value?.suggested_edges) {
    for (const se of suggestResult.value.suggested_edges) {
      if (se.source === c.local_id) {
        try {
          const relType = (se.relation as RelationType)
            || inferRelationType(c.node_type, selectedNode.value?.node_type ?? '')
          if (relType) {
            await upsertEdge({ source_id: adopted.id, target_id: se.target, relation_type: relType })
          }
        } catch { /* ignore */ }
      }
    }
  }
  suggestResult.value = null
}

const selectedNode = computed(() => state.graph?.nodes.find(n => n.id === state.selectedNodeId) ?? null)
const selectedEdge = computed(() => state.graph?.edges.find(e => e.id === state.selectedEdgeId) ?? null)

const nodeIssues = computed(() =>
  (state.graph?.issues ?? []).filter(i => i.node_id === selectedNode.value?.id),
)

const nodeTypeCounts = computed(() => {
  const counts: Partial<Record<NodeType, number>> = {}
  for (const n of state.graph?.nodes ?? []) {
    counts[n.node_type] = (counts[n.node_type] ?? 0) + 1
  }
  return counts
})

const TYPE_LABELS: Record<NodeType, string> = {
  claim: '主张', grounds: '依据', warrant: '论证保证',
  backing: '支撑', qualifier: '限定', rebuttal: '反驳',
}
function typeLabel(t: NodeType) { return TYPE_LABELS[t] ?? t }

const REL_LABELS: Record<RelationType, string> = {
  supports: '支持', warrants: '保证', backs: '支撑',
  qualifies: '限定', rebuts: '反驳', counters: '回应',
}
function relLabel(r: RelationType) { return REL_LABELS[r] ?? r }

function sevLabel(s: string) { return s === 'error' ? '错误' : s === 'warning' ? '警告' : '提示' }

function nodeText(nid: string) {
  const n = state.graph?.nodes.find(x => x.id === nid)
  return n ? (n.label || n.text).slice(0, 20) + (n.text.length > 20 ? '…' : '') : nid
}

const editText = ref('')
watch(selectedNode, n => { editText.value = n?.text ?? '' }, { immediate: true })

async function commitText() {
  if (!selectedNode.value || editText.value === selectedNode.value.text) return
  await upsertNode({ id: selectedNode.value.id, node_type: selectedNode.value.node_type, text: editText.value } as any)
}

async function deleteSelectedNode() {
  if (!selectedNode.value) return
  const id = selectedNode.value.id
  state.selectedNodeId = ''
  await deleteNode(id)
}

async function deleteSelectedEdge() {
  if (!selectedEdge.value) return
  const id = selectedEdge.value.id
  state.selectedEdgeId = ''
  await deleteEdge(id)
}

// ── Span list ─────────────────────────────────────────────────────────────────

const nodeSpans = computed(() =>
  (state.graph?.spans ?? []).filter(s => s.node_id === selectedNode.value?.id),
)

function jumpToSpan(spanId: string) {
  focusSpan(spanId)
}

async function removeSpan(spanId: string) {
  await deleteSpan(spanId)
}
</script>

<style scoped>
.arg-inspector {
  height: 100%;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.inspector-section { display: flex; flex-direction: column; gap: 8px; }

.inspector-title { font-size: 11px; font-weight: 600; color: var(--c-text-2); text-transform: uppercase; letter-spacing: 0.05em; margin: 0; }

.inspector-graph-title { font-size: 14px; font-weight: 600; color: var(--c-text-0); margin: 0; }

.inspector-stats { display: flex; flex-wrap: wrap; gap: 6px; }
.stat-item { display: flex; align-items: center; gap: 4px; font-size: 12px; color: var(--c-text-1); background: var(--c-surface-2); border-radius: var(--radius-sm); padding: 2px 7px; }
.stat-type { color: var(--c-text-2); }
.stat-count { font-weight: 600; color: var(--c-text-0); }

.inspector-issues-count { font-size: 12px; color: var(--c-warn-fg); background: var(--c-warn-bg); border-radius: var(--radius-sm); padding: 3px 8px; }

.inspector-node-type-badge {
  display: inline-flex;
  align-items: center;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 3px 10px;
  border-radius: 999px;
  border: 1.5px solid currentColor;
}
.inspector-node-type-badge.type-claim { color: var(--c-accent); }
.inspector-node-type-badge.type-grounds { color: #10b981; }
.inspector-node-type-badge.type-warrant { color: #3b82f6; }
.inspector-node-type-badge.type-backing { color: #93c5fd; }
.inspector-node-type-badge.type-qualifier { color: #f59e0b; }
.inspector-node-type-badge.type-rebuttal { color: var(--c-danger); }

.inspector-field { display: flex; flex-direction: column; gap: 4px; }
.inspector-label { font-size: 11px; color: var(--c-text-2); font-weight: 500; }

.inspector-textarea {
  background: var(--c-surface-2);
  border: 1px solid var(--c-surface-3);
  border-radius: var(--radius-sm);
  color: var(--c-text-0);
  font: inherit;
  font-size: 13px;
  padding: 6px 8px;
  resize: vertical;
  min-height: 72px;
  outline: none;
  transition: border-color 140ms;
}
.inspector-textarea:focus { border-color: var(--c-accent); }

.inspector-issue { display: flex; flex-direction: column; gap: 2px; padding: 6px 8px; border-radius: var(--radius-sm); background: var(--c-surface-2); border-left: 3px solid currentColor; }
.inspector-issue.sev-error { color: var(--c-danger); }
.inspector-issue.sev-warning { color: var(--c-warn-fg); }
.inspector-issue.sev-info { color: var(--c-text-2); }
.issue-sev { font-size: 10px; font-weight: 700; text-transform: uppercase; }
.issue-msg { font-size: 12px; color: var(--c-text-0); }
.issue-sug { font-size: 11px; color: var(--c-text-2); margin: 0; }

.inspector-placeholder { opacity: 0.5; }
.placeholder-text { font-size: 12px; color: var(--c-text-2); margin: 0; font-style: italic; }

.inspector-span {
  background: var(--c-surface-2);
  border-radius: var(--radius-sm);
  padding: 5px 7px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.span-quote {
  font-size: 11px;
  color: var(--c-text-1);
  font-style: italic;
  line-height: 1.4;
  word-break: break-all;
}

.span-actions { display: flex; gap: 4px; }

.span-action-btn {
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--c-surface-3);
  background: transparent;
  color: var(--c-text-1);
  font: inherit;
  font-size: 10px;
  cursor: pointer;
  transition: background 100ms;
}
.span-action-btn:hover { background: var(--c-surface-3); }
.span-action-btn--danger { color: var(--c-danger); }
.span-action-btn--danger:hover { background: var(--c-danger-bg); }

.inspector-edge-rel {
  font-size: 12px;
  font-weight: 700;
  padding: 3px 10px;
  border-radius: 999px;
  display: inline-flex;
  border: 1.5px solid currentColor;
}
.inspector-edge-rel.rel-supports { color: #10b981; }
.inspector-edge-rel.rel-warrants { color: #3b82f6; }
.inspector-edge-rel.rel-backs    { color: #93c5fd; }
.inspector-edge-rel.rel-qualifies { color: #f59e0b; }
.inspector-edge-rel.rel-rebuts   { color: var(--c-danger); }
.inspector-edge-rel.rel-counters { color: #f97316; }

.inspector-edge-info { font-size: 12px; color: var(--c-text-1); margin: 0; }

.inspector-actions { display: flex; flex-direction: column; gap: 6px; margin-top: auto; }
.inspector-btn {
  padding: 6px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--c-surface-3);
  background: var(--c-surface-2);
  color: var(--c-text-0);
  font: inherit;
  font-size: 13px;
  cursor: pointer;
  transition: background 140ms, border-color 140ms;
}
.inspector-btn:hover { background: var(--c-surface-3); }
.inspector-btn--danger { color: var(--c-danger); border-color: var(--c-danger-bg); }
.inspector-btn--danger:hover { background: var(--c-danger-bg); }
.inspector-btn--primary { background: var(--c-accent); color: #fff; border-color: var(--c-accent); }
.inspector-btn--primary:hover { opacity: 0.85; background: var(--c-accent); }
.inspector-btn:disabled { opacity: 0.45; cursor: not-allowed; }

.suggest-candidate {
  background: var(--c-surface-2);
  border-radius: var(--radius-sm);
  padding: 6px 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  border-left: 3px solid var(--c-accent);
}

.candidate-type {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.candidate-type.type-claim { color: var(--c-accent); }
.candidate-type.type-grounds { color: #10b981; }
.candidate-type.type-warrant { color: #3b82f6; }
.candidate-type.type-backing { color: #93c5fd; }
.candidate-type.type-qualifier { color: #f59e0b; }
.candidate-type.type-rebuttal { color: var(--c-danger); }

.candidate-text {
  font-size: 12px;
  color: var(--c-text-0);
  line-height: 1.5;
}

.candidate-adopt-btn {
  align-self: flex-start;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--c-accent);
  background: transparent;
  color: var(--c-accent);
  font: inherit;
  font-size: 11px;
  cursor: pointer;
  transition: background 100ms, color 100ms;
}
.candidate-adopt-btn:hover { background: var(--c-accent); color: #fff; }

.inspector-select {
  background: var(--c-surface-2);
  border: 1px solid var(--c-surface-3);
  border-radius: var(--radius-sm);
  color: var(--c-text-0);
  font: inherit;
  font-size: 12px;
  padding: 4px 6px;
  outline: none;
  cursor: pointer;
}
.inspector-select:focus { border-color: var(--c-accent); }

.export-msg {
  font-size: 11px;
  color: var(--c-text-2);
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  background: var(--c-surface-2);
  text-align: center;
}
.export-msg--ok { color: #10b981; background: color-mix(in srgb, #10b981 12%, transparent); }
</style>
