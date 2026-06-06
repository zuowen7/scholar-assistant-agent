<template>
  <div class="arg-mini">
    <template v-if="state.graph">
      <div class="arg-mini-header">
        <span class="arg-mini-title">{{ state.graph.title }}</span>
        <span
          v-if="state.graph.source_doc"
          class="arg-mini-linked"
          :title="t('argument.graphLinkedTooltip')"
        ></span>
        <button class="arg-mini-open" @click="openFull">{{ t('argument.openFull') }}</button>
      </div>
      <div class="arg-mini-canvas">
        <ArgumentMapCanvas :readonly="true" />
      </div>
    </template>
    <div v-else-if="state.extracting" class="arg-mini-extracting">
      <div class="arg-mini-extract-pill">
        <span class="dot-wave"><i></i><i></i><i></i></span>
        <span class="arg-mini-extract-text">{{ t('argument.extractingStructure') }}</span>
      </div>
      <div class="arg-mini-extract-track"></div>
    </div>
    <div v-else class="arg-mini-empty">
      <p>{{ t('argument.noArgMap') }}</p>
      <button
        class="arg-mini-extract-btn"
        :disabled="!hasContent || state.extracting"
        :title="hasContent ? t('argument.extractTooltip') : t('argument.openDocFirst')"
        @click="doExtract"
      >
        {{ state.extracting ? t('argument.extracting2') : t('argument.extractFromPaper') }}
      </button>
      <p v-if="!hasContent" class="arg-mini-hint">{{ t('argument.openDocFirst') }}</p>
      <p v-if="extractError" class="arg-mini-error">{{ extractError }}</p>
      <button class="arg-mini-open" @click="openFull">{{ t('argument.goToArgMap') }}</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
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
    await createGraph(t('argument.unnamedGraph'), activeTab.value?.path ?? undefined)
    await extractArgument(props.content)
  } catch (e) {
    extractError.value = e instanceof Error ? e.message : t('argument.extractFailedGeneric')
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
  transition: background var(--motion-fast) var(--ease-out), transform 0.06s ease;
}
.arg-mini-open:hover { background: var(--c-accent-bg2); }
.arg-mini-open:active { transform: scale(0.94); }

.arg-mini-linked {
  position: relative;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #4ade80;
  cursor: help;
  flex-shrink: 0;
}
.arg-mini-linked::after {
  content: '';
  position: absolute;
  inset: -3px;
  border-radius: 50%;
  border: 1.5px solid #4ade80;
  animation: sonar-ring 1.8s ease-out infinite;
}
@keyframes sonar-ring {
  0%   { transform: scale(1);   opacity: 0.7; }
  100% { transform: scale(2.6); opacity: 0; }
}

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
.arg-mini-extract-btn:active:not(:disabled) {
  transform: scale(0.94);
  filter: brightness(0.92);
  transition-duration: 0.04s;
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

/* Extracting state */
.arg-mini-extracting {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 18px;
}

.arg-mini-extract-pill {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 8px 20px;
  background: color-mix(in srgb, var(--c-accent) 10%, var(--c-surface-1));
  border: 1px solid color-mix(in srgb, var(--c-accent) 28%, transparent);
  border-radius: 20px;
  animation: pill-appear 0.25s ease-out;
}
@keyframes pill-appear {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0); }
}

.arg-mini-extract-text {
  font-size: 12px;
  color: var(--c-text-1);
  white-space: nowrap;
}

.dot-wave { display: flex; gap: 4px; align-items: center; }
.dot-wave i {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--c-accent); display: block;
  animation: wave-bounce 1.1s ease-in-out infinite;
}
.dot-wave i:nth-child(2) { animation-delay: 0.18s; }
.dot-wave i:nth-child(3) { animation-delay: 0.36s; }
@keyframes wave-bounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.25; }
  30%            { transform: translateY(-5px); opacity: 1; }
}

.arg-mini-extract-track {
  width: 100px;
  height: 2px;
  background: linear-gradient(
    90deg,
    transparent 0%,
    var(--c-accent) 45%,
    transparent 100%
  );
  background-size: 40% 100%;
  background-repeat: no-repeat;
  animation: extract-scan 1.4s ease-in-out infinite;
  border-radius: 1px;
}
@keyframes extract-scan {
  0%   { background-position: -40% 0; }
  100% { background-position: 140% 0; }
}
</style>
