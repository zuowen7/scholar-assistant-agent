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
    <div v-else class="arg-mini-empty">
      <p>尚无论证图</p>
      <button class="arg-mini-open" @click="openFull">前往论证地图</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useArgumentMap, requestOpenFullArgMap } from '../../composables/useArgumentMap'
import ArgumentMapCanvas from './ArgumentMapCanvas.vue'

const { state } = useArgumentMap()

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
