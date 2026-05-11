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

      <div class="inspector-actions">
        <button class="inspector-btn" @click="$emit('auto-layout')">自动布局</button>
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

        <!-- Span list: Phase 3 placeholder -->
        <div class="inspector-field inspector-placeholder">
          <label class="inspector-label">原文引用</label>
          <p class="placeholder-text">绑定原文段落（Phase 3 实现）</p>
        </div>
      </div>

      <div class="inspector-actions">
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
import type { NodeType, RelationType } from '../../composables/useArgumentMap'
import { useArgumentMap } from '../../composables/useArgumentMap'

defineEmits<{ 'auto-layout': [] }>()

const { state, upsertNode, deleteNode, deleteEdge } = useArgumentMap()

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
</style>
