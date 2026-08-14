<template>
  <div class="arg-view">
    <!-- Toolbar -->
    <div class="arg-view-toolbar">
      <div class="arg-view-left">
        <span class="arg-view-brand">{{ t('argument.argumentMap') }}</span>
        <!-- Graph selector -->
        <select
          v-if="state.graphList.length"
          class="arg-graph-select"
          :value="state.graph?.id ?? ''"
          @change="onSelectGraph"
        >
          <option value="">{{ t('argument.selectGraph') }}</option>
          <option v-for="g in state.graphList" :key="g.id" :value="g.id">
            {{ g.title }} ({{ t('argument.nodesCount', { count: g.node_count }) }})
          </option>
        </select>
      </div>

      <div class="arg-view-right">
        <button class="arg-toolbar-btn" @click="runAutoLayout">
          {{ t('argument.autoLayout') }}
        </button>
        <button class="arg-toolbar-btn" @click="showNewGraph = true">
          {{ t('argument.newGraph') }}
        </button>
        <template v-if="state.graph">
          <span class="arg-toolbar-separator" />
          <select
            v-model="newNodeType"
            class="arg-node-select"
            :aria-label="t('argument.contentLabel')"
          >
            <option v-for="option in nodeTypes" :key="option.value" :value="option.value">
              {{ option.label }}
            </option>
          </select>
          <button class="arg-toolbar-btn arg-toolbar-btn--primary" @click="addNode(newNodeType)">
            + {{ t('general.add') }}
          </button>
        </template>
      </div>
    </div>

    <!-- Main area -->
    <div class="arg-view-body">
      <!-- Graph list (when no graph selected) -->
      <div v-if="!state.graph && !state.graphList.length" class="arg-view-empty">
        <p>{{ t('argument.noGraph') }}</p>
        <button class="arg-primary-btn" @click="showNewGraph = true">
          {{ t('argument.newGraph') }}
        </button>
      </div>

      <div v-else-if="!state.graph" class="arg-view-empty">
        <p>{{ t('argument.graphPlaceholder') }}</p>
      </div>

      <template v-else>
        <!-- Three-column: source | canvas | inspector -->
        <div class="arg-view-split">
          <div class="arg-source-area">
            <ArgSourcePane />
          </div>
          <div class="arg-canvas-area">
            <ArgumentMapCanvas ref="canvasRef" />
          </div>
          <div class="arg-inspector-area">
            <ArgInspector @auto-layout="runAutoLayout" />
          </div>
        </div>
      </template>
    </div>

    <AppPromptDialog
      v-model="showNewGraph"
      :title="t('argument.newGraph')"
      :description="t('argument.graphPlaceholder')"
      :label="t('argument.graphTitle')"
      :placeholder="t('argument.graphTitle')"
      :confirm-label="t('argument.create2')"
      :cancel-label="t('general.cancel')"
      @submit="createNewGraph"
    />
  </div>
</template>

<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
import type { NodeType } from '../../composables/useArgumentMap'
import { useArgumentMap } from '../../composables/useArgumentMap'
import { useArgumentLayout } from '../../composables/useArgumentLayout'
import ArgumentMapCanvas from './ArgumentMapCanvas.vue'
import ArgInspector from './ArgInspector.vue'
import ArgSourcePane from './ArgSourcePane.vue'
import AppPromptDialog from '../shell/AppPromptDialog.vue'

const { state, listGraphs, createGraph, loadGraph, upsertNode } = useArgumentMap()
const { autoLayout } = useArgumentLayout()

const showNewGraph = ref(false)
const newNodeType = ref<NodeType>('claim')
const canvasRef = ref<{ fitCanvas: () => void } | null>(null)

const nodeTypes = [
  { value: 'claim' as NodeType, label: t('argument.claim') },
  { value: 'grounds' as NodeType, label: t('argument.grounds') },
  { value: 'warrant' as NodeType, label: t('argument.warrant') },
  { value: 'backing' as NodeType, label: t('argument.backing') },
  { value: 'qualifier' as NodeType, label: t('argument.qualifier') },
  { value: 'rebuttal' as NodeType, label: t('argument.rebuttal') },
]

onMounted(async () => {
  await listGraphs()
  if (state.graphList.length && !state.graph) {
    await loadGraph(state.graphList[0].id)
  }
  if (needsLayout()) await runAutoLayout()
  else await fitCanvas()
})

async function onSelectGraph(e: Event) {
  const gid = (e.target as HTMLSelectElement).value
  if (!gid) return
  await loadGraph(gid)
  if (needsLayout()) await runAutoLayout()
  else await fitCanvas()
}

async function createNewGraph(title: string) {
  if (!title.trim()) return
  await createGraph(title.trim())
  await listGraphs()
  showNewGraph.value = false
}

async function addNode(node_type: NodeType) {
  const label = {
    claim: t('argument.newClaim'),
    grounds: t('argument.newGrounds'),
    warrant: t('argument.newWarrant'),
    backing: t('argument.newBacking'),
    qualifier: t('argument.newQualifier'),
    rebuttal: t('argument.newRebuttal'),
  }[node_type]
  await upsertNode({ node_type, text: label })
}

function needsLayout() {
  const nodes = state.graph?.nodes ?? []
  if (nodes.length < 2) return false
  const positioned = nodes.filter(
    (node) => Number.isFinite(node.position?.x) && Number.isFinite(node.position?.y),
  )
  if (positioned.length < nodes.length) return true
  const unique = new Set(
    positioned.map(
      (node) => `${Math.round(node.position!.x / 20)}:${Math.round(node.position!.y / 20)}`,
    ),
  )
  return unique.size < Math.ceil(nodes.length * 0.6)
}

async function fitCanvas() {
  await nextTick()
  requestAnimationFrame(() => canvasRef.value?.fitCanvas())
}

async function runAutoLayout() {
  if (!state.graph) return
  const positioned = autoLayout(state.graph.nodes, state.graph.edges, 'LR')
  for (const p of positioned) {
    const node = state.graph!.nodes.find((n) => n.id === p.id)
    if (node) node.position = p.position
  }
  await fitCanvas()
}
</script>

<style scoped>
.arg-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--c-app-bg);
  overflow: hidden;
}

/* Toolbar */
.arg-view-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 50px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--c-border);
  background: var(--c-panel);
  flex-shrink: 0;
  gap: 10px;
  flex-wrap: wrap;
}

.arg-view-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
}

.arg-view-brand {
  font-size: 13px;
  font-weight: 700;
  color: var(--c-text-0);
  white-space: nowrap;
  letter-spacing: var(--tracking-tight);
}

.arg-graph-select {
  flex: 1;
  min-width: 0;
  max-width: 240px;
  background: var(--c-surface-1);
  border: 1px solid var(--c-border);
  border-radius: 8px;
  color: var(--c-text-0);
  font: inherit;
  font-size: 12px;
  padding: 3px 8px;
  outline: none;
}

.arg-view-right {
  display: flex;
  align-items: center;
  gap: 5px;
  flex-wrap: wrap;
}

.arg-toolbar-separator {
  width: 1px;
  height: 24px;
  margin: 0 3px;
  background: var(--c-border);
}
.arg-node-select {
  height: 34px;
  border: 1px solid var(--c-border);
  border-radius: 8px;
  background: var(--c-surface-1);
  color: var(--c-text-1);
  padding: 0 28px 0 9px;
  font: inherit;
  font-size: 12px;
}

.arg-toolbar-btn {
  height: 34px;
  padding: 0 11px;
  border-radius: 8px;
  border: 1px solid var(--c-border);
  background: var(--c-panel);
  color: var(--c-text-0);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  transition:
    background 140ms,
    border-color 140ms;
  white-space: nowrap;
}
.arg-toolbar-btn:hover {
  border-color: var(--c-border-strong);
  background: var(--c-surface-2);
}
.arg-toolbar-btn--primary {
  border-color: var(--c-accent);
  background: var(--c-accent);
  color: white;
}
.arg-toolbar-btn--primary:hover {
  border-color: var(--c-accent-hover);
  background: var(--c-accent-hover);
}

/* Body */
.arg-view-body {
  flex: 1;
  min-height: 0;
  display: flex;
  overflow: hidden;
}

.arg-view-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  color: var(--c-text-2);
  font-size: 14px;
}

.arg-view-split {
  display: grid;
  /* 弹性列宽：右侧 Agent 面板打开时容器只有 ~796px，固定 220/360/260 会溢出 44px */
  grid-template-columns: minmax(150px, 0.9fr) minmax(300px, 1.6fr) minmax(200px, 1fr);
  width: 100%;
  height: 100%;
  overflow: hidden;
}

.arg-source-area {
  min-width: 0;
  height: 100%;
  overflow: hidden;
}

.arg-canvas-area {
  flex: 1;
  min-width: 0;
  height: 100%;
  /* 节点超出画布边界时裁剪，避免压到右侧属性面板 */
  overflow: hidden;
}

.arg-inspector-area {
  min-width: 0;
  border-left: 1px solid var(--c-border);
  background: var(--c-panel);
  height: 100%;
  overflow-y: auto;
}

/* Buttons */
.arg-primary-btn {
  padding: 6px 16px;
  border-radius: var(--radius-sm);
  border: none;
  background: var(--c-accent);
  color: #fff;
  font: inherit;
  font-size: 13px;
  cursor: pointer;
  transition: background 140ms;
}
.arg-primary-btn:hover {
  background: var(--c-accent-hover);
}
.arg-primary-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.arg-ghost-btn {
  padding: 6px 16px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--c-surface-3);
  background: transparent;
  color: var(--c-text-1);
  font: inherit;
  font-size: 13px;
  cursor: pointer;
}
.arg-ghost-btn:hover {
  background: var(--c-surface-2);
}

@media (max-width: 1100px) {
  .arg-view-split {
    grid-template-columns: 190px minmax(300px, 1fr) 230px;
  }
  .arg-view-toolbar {
    align-items: flex-start;
  }
}
</style>
