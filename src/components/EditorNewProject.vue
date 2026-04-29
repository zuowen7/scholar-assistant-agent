<template>
  <div v-if="visible" class="project-start-backdrop" @click.self="$emit('close')">
    <div class="project-start-dialog">
      <div class="project-start-header">
        <div>
          <div class="welcome-kicker">新建工程</div>
          <h3>新建工程</h3>
        </div>
        <button class="project-start-close" aria-label="关闭" @click="$emit('close')">
          <X :size="18" :stroke-width="2" />
        </button>
      </div>
      <div class="project-start-options">
        <button class="project-start-option primary" @click="$emit('enter-editor')">
          <strong>直接进入编辑器</strong>
          <span>创建空白文档，保持现有写作流程。</span>
        </button>
        <div class="project-start-option">
          <strong>先创建思维导图</strong>
          <span>先梳理论文结构，再保存并进入编辑器。</span>
          <div class="project-topic-row">
            <input
              v-model="topic"
              class="project-topic-input"
              placeholder="输入研究主题（可选）"
              @keydown.enter="$emit('enter-mindmap', topic)"
            />
            <button class="project-topic-go" @click="$emit('enter-mindmap', topic)">创建</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { X } from './ui/icons'

defineProps<{ visible: boolean }>()

const emit = defineEmits<{
  close: []
  'enter-editor': []
  'enter-mindmap': [topic: string]
}>()

const topic = ref('')
</script>

<style scoped>
.project-start-backdrop {
  position: fixed;
  inset: 0;
  z-index: 80;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--c-overlay);
  backdrop-filter: blur(4px);
}

.project-start-dialog {
  width: min(520px, calc(100vw - 48px));
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  background: var(--panel-bg);
  color: var(--text-primary);
  box-shadow: var(--elevation-4);
}

.project-start-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  padding: 18px 20px;
  border-bottom: 1px solid var(--border-color);
}
.project-start-header h3 { margin: 4px 0 0; font-size: 20px; }

.welcome-kicker {
  color: var(--c-accent);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.project-start-close {
  border: 0;
  background: transparent;
  color: var(--c-text-3);
  cursor: pointer;
  display: flex;
  align-items: center;
  padding: 4px;
  border-radius: 4px;
}
.project-start-close:hover { color: var(--c-text-0); background: var(--hover-bg); }

.project-start-options { display: grid; gap: 10px; padding: 18px 20px 20px; }

.project-start-option {
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--toolbar-bg);
  color: var(--text-primary);
  text-align: left;
  padding: 14px 16px;
  cursor: pointer;
  font: inherit;
}
.project-start-option:hover { border-color: var(--c-accent); background: var(--hover-bg); }
.project-start-option.primary {
  background: color-mix(in srgb, var(--c-accent) 18%, var(--toolbar-bg));
  border-color: color-mix(in srgb, var(--c-accent) 55%, var(--border-color));
}
.project-start-option strong { display: block; margin-bottom: 5px; font-size: 14px; }
.project-start-option span { color: var(--c-text-3); font-size: 12px; line-height: 1.5; }

.project-topic-row { display: flex; gap: 8px; margin-top: 10px; }

.project-topic-input {
  flex: 1;
  height: 32px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--editor-bg);
  color: var(--text-primary);
  padding: 0 10px;
  font: inherit;
  font-size: 13px;
  outline: none;
}
.project-topic-input:focus { border-color: var(--c-accent); }

.project-topic-go {
  height: 32px;
  border: 1px solid var(--c-accent);
  border-radius: var(--radius-sm);
  background: var(--c-accent);
  color: #fff;
  padding: 0 16px;
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.project-topic-go:hover { opacity: 0.88; }
</style>
