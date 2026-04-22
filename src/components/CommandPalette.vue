<template>
    <div
      v-if="visible"
      class="cmd-palette"
      :style="{ top: position.y + 'px', left: position.x + 'px' }"
    >
      <!-- 任务类型切换 -->
      <div class="cmd-task-tabs">
        <button
          v-for="t in taskTypes"
          :key="t.id"
          class="cmd-tab"
          :class="{ active: activeTask === t.id }"
          @click="activeTask = t.id"
        >{{ t.label }}</button>
      </div>

      <!-- 快捷说明 -->
      <div v-if="activeTask === 'coherence'" class="cmd-hint">
        已自动传入前一段作为上下文
      </div>

      <!-- 输入区 -->
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
        <button class="cmd-submit" @click="handleSubmit" :disabled="loading">
          <span v-if="!loading">Apply</span>
          <span v-else class="cmd-spinner"></span>
        </button>
      </div>

      <!-- 预设按钮 -->
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
    label: '润色',
    placeholder: 'AI instruction (Enter to apply, Esc to cancel)...',
    presets: [
      { label: 'Academic Polish', instruction: 'Polish for formal academic English' },
      { label: 'Concise', instruction: 'Make more concise without losing meaning' },
      { label: 'Fix Grammar', instruction: 'Fix grammar and improve clarity' },
    ],
  },
  {
    id: 'expand',
    label: '扩写',
    placeholder: 'Describe how to expand...',
    presets: [
      { label: 'Expand', instruction: 'Expand into a complete academic paragraph' },
      { label: 'Shorten', instruction: 'Condense into fewer sentences' },
    ],
  },
  {
    id: 'coherence',
    label: '连贯性',
    placeholder: 'Describe the section goal...',
    presets: [
      { label: 'Connect to Prev', instruction: 'Improve transition from previous paragraph' },
      { label: 'Section Flow', instruction: 'Better serve the section goal' },
    ],
  },
  {
    id: 'grammar',
    label: '语法',
    placeholder: 'Describe the fix...',
    presets: [
      { label: 'Fix Grammar', instruction: 'Fix grammar and spelling errors' },
      { label: 'Improve Clarity', instruction: 'Improve sentence clarity and readability' },
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
    previous: '',  // MonacoEditor 从 editor API 获取前一段
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
  background: #1f1f1f;
  border: 1px solid #007acc;
  border-radius: 8px;
  padding: 8px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.5);
  min-width: 380px;
  max-width: 500px;
}

.cmd-task-tabs {
  display: flex;
  gap: 2px;
  margin-bottom: 6px;
  background: #181818;
  border-radius: 6px;
  padding: 2px;
}

.cmd-tab {
  flex: 1;
  background: none;
  border: none;
  border-radius: 4px;
  padding: 3px 6px;
  color: #888;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}
.cmd-tab:hover { color: #ddd; background: #2a2a2a; }
.cmd-tab.active { background: #007acc; color: #fff; }

.cmd-hint {
  font-size: 11px;
  color: #666;
  padding: 2px 4px;
  margin-bottom: 4px;
}

.cmd-input-row {
  display: flex;
  gap: 6px;
}

.cmd-input {
  flex: 1;
  background: #2d2d2d;
  border: 1px solid #444;
  border-radius: 4px;
  padding: 6px 10px;
  color: #ddd;
  font-size: 13px;
  outline: none;
}
.cmd-input:focus { border-color: #007acc; }
.cmd-input::placeholder { color: #666; }

.cmd-submit {
  background: #007acc;
  border: none;
  border-radius: 4px;
  padding: 6px 14px;
  color: #fff;
  font-size: 12px;
  cursor: pointer;
  min-width: 60px;
}
.cmd-submit:hover { opacity: 0.9; }
.cmd-submit:disabled { opacity: 0.5; }

.cmd-presets {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  margin-top: 6px;
}

.cmd-presets button {
  background: #333;
  border: 1px solid #444;
  border-radius: 10px;
  padding: 2px 10px;
  color: #aaa;
  font-size: 11px;
  cursor: pointer;
}
.cmd-presets button:hover { background: #444; color: #ddd; }

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
