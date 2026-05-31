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
        <button class="arg-toolbar-btn" @click="runAutoLayout">{{ t('argument.autoLayout') }}</button>
        <button class="arg-toolbar-btn" @click="showNewGraph = true">{{ t('argument.newGraph') }}</button>
        <!-- Add node buttons -->
        <template v-if="state.graph">
          <button
            v-for="t in nodeTypes"
            :key="t.value"
            class="arg-toolbar-btn arg-add-node"
            :class="`type-${t.value}`"
            @click="addNode(t.value)"
          >
            + {{ t.label }}
          </button>
        </template>
      </div>
    </div>

    <!-- Main area -->
    <div class="arg-view-body">
      <!-- Graph list (when no graph selected) -->
      <div v-if="!state.graph && !state.graphList.length" class="arg-view-empty">
        <p>{{ t('argument.noGraph') }}</p>
        <button class="arg-primary-btn" @click="showNewGraph = true">{{ t('argument.newGraph') }}</button>
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
            <ArgumentMapCanvas />
          </div>
          <div class="arg-inspector-area">
            <ArgInspector @auto-layout="runAutoLayout" />
          </div>
        </div>
      </template>
    </div>

    <!-- New graph dialog -->
    <Teleport to="body">
      <div v-if="showNewGraph" class="arg-dialog-overlay" @click.self="showNewGraph = false">
        <div class="arg-dialog">
          <p class="arg-dialog-title">{{ t('argument.newGraph') }}</p>
          <input
            v-model="newGraphTitle"
            class="arg-dialog-input"
            :placeholder="t('argument.graphTitle')"
            @keydown.enter="createNewGraph"
            @keydown.escape="showNewGraph = false"
          />
          <div class="arg-dialog-actions">
            <button class="arg-primary-btn" :disabled="!newGraphTitle.trim()" @click="createNewGraph">{{ t('argument.create2') }}</button>
            <button class="arg-ghost-btn" @click="showNewGraph = false">{{ t('argument.cancel') }}</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
import type { NodeType } from '../../composables/useArgumentMap'
import { useArgumentMap } from '../../composables/useArgumentMap'
import { useArgumentLayout } from '../../composables/useArgumentLayout'
import ArgumentMapCanvas from './ArgumentMapCanvas.vue'
import ArgInspector from './ArgInspector.vue'
import ArgSourcePane from './ArgSourcePane.vue'

const { state, listGraphs, createGraph, loadGraph, upsertNode } = useArgumentMap()
const { autoLayout } = useArgumentLayout()

const showNewGraph = ref(false)
const newGraphTitle = ref('')

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
})

async function onSelectGraph(e: Event) {
  const gid = (e.target as HTMLSelectElement).value
  if (gid) await loadGraph(gid)
}

async function createNewGraph() {
  if (!newGraphTitle.value.trim()) return
  await createGraph(newGraphTitle.value.trim())
  await listGraphs()
  newGraphTitle.value = ''
  showNewGraph.value = false
}

async function addNode(node_type: NodeType) {
  const label = {
    claim: t('argument.newClaim'), grounds: t('argument.newGrounds'), warrant: t('argument.newWarrant'),
    backing: t('argument.newBacking'), qualifier: t('argument.newQualifier'), rebuttal: t('argument.newRebuttal'),
  }[node_type]
  await upsertNode({ node_type, text: label } as any)
}

function runAutoLayout() {
  if (!state.graph) return
  const positioned = autoLayout(state.graph.nodes as any[], state.graph.edges as any[])
  for (const p of positioned) {
    const node = state.graph!.nodes.find(n => n.id === p.id)
    if (node) node.position = p.position
  }
}
</script>

<style scoped>
.arg-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--c-surface-0);
  overflow: hidden;
}

/* Toolbar */
.arg-view-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid var(--c-surface-2);
  background: var(--c-surface-1);
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
  color: var(--c-accent);
  white-space: nowrap;
  letter-spacing: var(--tracking-tight);
}

.arg-graph-select {
  flex: 1;
  min-width: 0;
  max-width: 240px;
  background: var(--c-surface-2);
  border: 1px solid var(--c-surface-3);
  border-radius: var(--radius-sm);
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

.arg-toolbar-btn {
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--c-surface-3);
  background: var(--c-surface-2);
  color: var(--c-text-0);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  transition: background 140ms, border-color 140ms;
  white-space: nowrap;
}
.arg-toolbar-btn:hover { background: var(--c-surface-3); }

.arg-add-node.type-claim { border-color: var(--c-accent); color: var(--c-accent); }
.arg-add-node.type-grounds { border-color: #10b981; color: #10b981; }
.arg-add-node.type-warrant { border-color: #3b82f6; color: #3b82f6; }
.arg-add-node.type-backing { border-color: #93c5fd; color: #93c5fd; }
.arg-add-node.type-qualifier { border-color: #f59e0b; color: #f59e0b; }
.arg-add-node.type-rebuttal { border-color: var(--c-danger); color: var(--c-danger); }

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
  display: flex;
  width: 100%;
  height: 100%;
  overflow: hidden;
}

.arg-source-area {
  width: 280px;
  flex-shrink: 0;
  height: 100%;
  overflow: hidden;
}

.arg-canvas-area {
  flex: 1;
  min-width: 0;
  height: 100%;
}

.arg-inspector-area {
  width: 240px;
  flex-shrink: 0;
  border-left: 1px solid var(--c-surface-2);
  background: var(--c-surface-1);
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
.arg-primary-btn:hover { background: var(--c-accent-hover); }
.arg-primary-btn:disabled { opacity: 0.45; cursor: not-allowed; }

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
.arg-ghost-btn:hover { background: var(--c-surface-2); }

/* Dialog */
.arg-dialog-overlay {
  position: fixed;
  inset: 0;
  background: var(--c-overlay);
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
}

.arg-dialog {
  background: var(--c-surface-1);
  border: 1px solid var(--c-surface-3);
  border-radius: var(--radius-lg);
  padding: 20px 24px;
  width: 360px;
  box-shadow: var(--shadow-lg);
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.arg-dialog-title { font-size: 14px; font-weight: 600; color: var(--c-text-0); margin: 0; }

.arg-dialog-input {
  background: var(--c-surface-2);
  border: 1px solid var(--c-surface-3);
  border-radius: var(--radius-sm);
  color: var(--c-text-0);
  font: inherit;
  font-size: 13px;
  padding: 7px 10px;
  outline: none;
  transition: border-color 140ms;
}
.arg-dialog-input:focus { border-color: var(--c-accent); }

.arg-dialog-actions { display: flex; gap: 8px; justify-content: flex-end; }
</style>
