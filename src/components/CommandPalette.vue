<template>
    <div
      v-if="visible"
      class="cmd-palette"
      :style="{ top: position.y + 'px', left: position.x + 'px' }"
      role="dialog"
      :aria-label="t('commandPalette.aiCommand')"
    >
      <div class="cmd-task-tabs" role="tablist">
        <button
          v-for="t in taskTypes"
          :key="t.id"
          class="cmd-tab"
          role="tab"
          :class="{ active: activeTask === t.id }"
          :aria-selected="activeTask === t.id"
          @click="activeTask = t.id"
        >{{ t.label }}</button>
      </div>

      <div v-if="activeTask === 'coherence'" class="cmd-hint">
        已自动带入前一段作为上下文
      </div>

      <div class="cmd-input-row">
        <input
          ref="inputRef"
          v-model="instruction"
          class="cmd-input"
          :placeholder="currentTask.placeholder"
          @keydown.enter="handleSubmit"
          @keydown.escape="$emit('cancel')"
          @keydown.stop
        />
        <button class="cmd-submit" @click="handleSubmit" :disabled="loading" :aria-label="t('commandPalette.execute')">
          <span v-if="!loading">{{ t('commandPalette.apply') }}</span>
          <span v-else class="cmd-spinner"></span>
        </button>
      </div>

      <div class="cmd-presets">
        <button
          v-for="p in currentTask.presets"
          :key="p.label"
          @click="setAndSubmit(p.instruction)"
        >{{ p.label }}</button>
      </div>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, watch } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps<{
  visible?: boolean
  position: { x: number; y: number }
  loading: boolean
  selectedText: string
}>()

const emit = defineEmits<{
  (e: 'submit', payload: { instruction: string; taskType: string; previous: string }): void
  (e: 'cancel'): void
}>()

const instruction = ref('')
const activeTask = ref('polish')
const inputRef = ref<HTMLInputElement>()

interface TaskType {
  id: string
  label: string
  placeholder: string
  presets: { label: string; instruction: string }[]
}

const taskTypes: TaskType[] = [
  {
    id: 'polish',
    label: t('commandPalette.polishLabel'),
    placeholder: t('commandPalette.polishPlaceholder'),
    presets: [
      { label: t('commandPalette.academicPolish'), instruction: 'Polish for formal academic English' },
      { label: t('commandPalette.moreConcise'), instruction: 'Make more concise without losing meaning' },
      { label: t('commandPalette.fixGrammar'), instruction: 'Fix grammar and improve clarity' },
    ],
  },
  {
    id: 'expand',
    label: t('commandPalette.expandLabel'),
    placeholder: t('commandPalette.expandPlaceholder'),
    presets: [
      { label: t('commandPalette.expandToParagraph'), instruction: 'Expand into a complete academic paragraph' },
      { label: t('commandPalette.condenseExpression'), instruction: 'Condense into fewer sentences' },
    ],
  },
  {
    id: 'coherence',
    label: t('commandPalette.coherenceLabel'),
    placeholder: t('commandPalette.coherencePlaceholder'),
    presets: [
      { label: t('commandPalette.transitionPrev'), instruction: 'Improve transition from previous paragraph' },
      { label: t('commandPalette.improveFlow'), instruction: 'Better serve the section goal' },
    ],
  },
  {
    id: 'grammar',
    label: t('commandPalette.grammarLabel'),
    placeholder: t('commandPalette.grammarPlaceholder'),
    presets: [
      { label: '修正语法', instruction: 'Fix grammar and spelling errors' },
      { label: t('commandPalette.improveClarity'), instruction: 'Improve sentence clarity and readability' },
    ],
  },
]

const currentTask = computed(() =>
  taskTypes.find(t => t.id === activeTask.value) || taskTypes[0]
)

watch(() => props.visible, async (v) => {
  if (v) {
    instruction.value = ''
    activeTask.value = 'polish'
    await nextTick()
    inputRef.value?.focus()
  }
})

function handleSubmit() {
  const inst = instruction.value.trim() || currentTask.value.presets[0].instruction
  emit('submit', {
    instruction: inst,
    taskType: activeTask.value,
    previous: '',
  })
}

function setAndSubmit(text: string) {
  instruction.value = text
  emit('submit', {
    instruction: text,
    taskType: activeTask.value,
    previous: '',
  })
}
</script>

<style scoped>
.cmd-palette {
  position: fixed;
  z-index: 9999;
  background: var(--c-surface-2);
  border: 1px solid var(--c-accent);
  border-radius: var(--radius-md);
  padding: 8px;
  box-shadow: var(--elevation-4);
  min-width: 380px;
  max-width: 500px;
}

.cmd-task-tabs {
  display: flex;
  gap: 2px;
  margin-bottom: 6px;
  background: var(--c-surface-1);
  border-radius: var(--radius-sm);
  padding: 2px;
}

.cmd-tab {
  flex: 1;
  background: none;
  border: none;
  border-radius: var(--radius-xs);
  padding: 4px 6px;
  color: var(--c-text-3);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: all var(--motion-fast);
  font-family: inherit;
}
.cmd-tab:hover { color: var(--c-text-0); background: var(--c-surface-3); }
.cmd-tab.active { background: var(--c-accent); color: #fff; }

.cmd-hint {
  font-size: var(--text-xs);
  color: var(--c-text-3);
  padding: 2px 4px;
  margin-bottom: 4px;
}

.cmd-input-row {
  display: flex;
  gap: 6px;
}

.cmd-input {
  flex: 1;
  background: var(--c-surface-1);
  border: 1px solid var(--c-surface-3);
  border-radius: var(--radius-sm);
  padding: 7px 10px;
  color: var(--c-text-0);
  font-size: var(--text-md);
  outline: none;
  font-family: inherit;
}
.cmd-input:focus { border-color: var(--c-accent); }
.cmd-input::placeholder { color: var(--c-text-3); }

.cmd-submit {
  background: var(--c-accent);
  border: none;
  border-radius: var(--radius-sm);
  padding: 7px 14px;
  color: #fff;
  font-size: var(--text-sm);
  cursor: pointer;
  min-width: 60px;
  font-family: inherit;
  transition: opacity var(--motion-fast);
}
.cmd-submit:hover:not(:disabled) { opacity: 0.88; }
.cmd-submit:disabled { opacity: 0.5; cursor: not-allowed; }

.cmd-presets {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  margin-top: 6px;
}

.cmd-presets button {
  background: var(--c-surface-3);
  border: 1px solid var(--c-surface-4);
  border-radius: var(--radius-pill);
  padding: 2px 10px;
  color: var(--c-text-2);
  font-size: var(--text-xs);
  cursor: pointer;
  font-family: inherit;
  transition: all var(--motion-fast);
}
.cmd-presets button:hover { background: var(--c-surface-4); color: var(--c-text-0); }

.cmd-spinner {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
