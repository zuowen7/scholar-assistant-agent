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
        :disabled="!hasContent || state.extracting"
        :title="hasContent ? '从当前编辑器内容提取 Toulmin 论证结构' : '请先在编辑器中打开文档'"
        @click="doExtract"
      >
        {{ state.extracting ? '提取中…' : '从论文提取论证图' }}
      </button>
      <p v-if="!hasContent" class="arg-mini-hint">请先在编辑器中打开文档</p>
      <p v-if="extractError" class="arg-mini-error">{{ extractError }}</p>
      <button class="arg-mini-open" @click="openFull">前往论证地图</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useArgumentMap, requestOpenFullArgMap, loadSourceFromEditor } from '../../composables/useArgumentMap'
import { useEditor } from '../../composables/useEditor'
import ArgumentMapCanvas from './ArgumentMapCanvas.vue'

const props = defineProps<{ content?: string }>()

const { state, createGraph, extractArgument } = useArgumentMap()
const { activeTab } = useEditor()

const extractError = ref('')

const hasContent = computed(() => !!(props.content?.trim()))

async function doExtract() {
  if (!props.content?.trim()) return
  extractError.value = ''
  try {
    // Bind the graph to the active file path so the Agent can locate it by file
    // (read_argument_graph(file_path=...)). Untitled tabs have no path → undefined.
    await createGraph('论证图', activeTab.value?.path ?? undefined)
    await extractArgument(props.content)
  } catch (e) {
    extractError.value = e instanceof Error ? e.message : '提取失败，请检查后端连接'
  }
}

function openFull() {
  // Pre-load editor content so the extract button is immediately usable in full view
  if (props.content?.trim()) loadSourceFromEditor()
  requestOpenFullArgMap()
}
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

.arg-mini-hint {
  font-size: 11px;
  color: var(--c-text-2);
  margin: 0;
  font-style: italic;
}

.arg-mini-error {
  font-size: 11px;
  color: var(--c-danger);
  margin: 0;
  text-align: center;
  max-width: 200px;
}
</style>
