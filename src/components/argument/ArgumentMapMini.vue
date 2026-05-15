<template>
  <div class="arg-mini">
    <template v-if="state.graph">
      <div class="arg-mini-header">
        <span class="arg-mini-title">{{ state.graph.title }}</span>
        <button class="arg-mini-open" @click="openFull">全屏打开</button>
      </div>
      <div class="arg-mini-canvas">
        <ArgumentMapCanvas :readonly="true" />
      </div>
    </template>
    <div v-else-if="state.extracting" class="arg-mini-empty">
      <p>正在提取论证结构…</p>
    </div>
    <div v-else class="arg-mini-empty">
      <p>尚无论证图</p>
      <button
        class="arg-mini-extract-btn"
        :disabled="!hasContent"
        @click="doExtract"
      >
        从论文提取论证图
      </button>
      <button class="arg-mini-open" @click="openFull">前往论证地图</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useArgumentMap, requestOpenFullArgMap } from '../../composables/useArgumentMap'
import ArgumentMapCanvas from './ArgumentMapCanvas.vue'

const props = defineProps<{ content?: string }>()

const { state, createGraph, extractArgument } = useArgumentMap()

const hasContent = computed(() => !!(props.content?.trim()))

async function doExtract() {
  if (!props.content?.trim()) return
  try {
    await createGraph('论证图', undefined)
    await extractArgument(props.content)
  } catch { /* ignore */ }
}

function openFull() { requestOpenFullArgMap() }
</script>

<style scoped>
.arg-mini {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--c-surface-0);
  overflow: hidden;
}

.arg-mini-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 10px;
  border-bottom: 1px solid var(--c-surface-2);
  flex-shrink: 0;
}

.arg-mini-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--c-text-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}

.arg-mini-open {
  font-size: 11px;
  color: var(--c-accent);
  background: none;
  border: none;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: var(--radius-xs);
  white-space: nowrap;
  flex-shrink: 0;
}
.arg-mini-open:hover { background: var(--c-accent-bg2); }

.arg-mini-extract-btn {
  font-size: 12px;
  padding: 6px 14px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--c-accent);
  background: transparent;
  color: var(--c-accent);
  cursor: pointer;
  margin-bottom: 6px;
}
.arg-mini-extract-btn:hover:not(:disabled) {
  background: var(--c-accent);
  color: #000;
}
.arg-mini-extract-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.arg-mini-canvas {
  flex: 1;
  min-height: 0;
}

.arg-mini-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--c-text-2);
  font-size: 13px;
}
</style>
