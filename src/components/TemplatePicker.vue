<template>
  <div v-if="visible" class="template-picker-overlay" @click.self="close">
    <div class="template-picker">
      <div class="tp-header">
        <h3>新建论文</h3>
        <button class="tp-close" @click="close">&times;</button>
      </div>

      <div class="tp-body">
        <div class="tp-grid">
          <div
            v-for="t in templates"
            :key="t.id"
            class="tp-card"
            :class="{ active: selected === t.id }"
            @click="selected = t.id"
          >
            <div class="tp-card-icon">{{ t.icon }}</div>
            <div class="tp-card-info">
              <div class="tp-card-name">{{ t.name }}</div>
              <div class="tp-card-venue">{{ t.venue }}</div>
              <div class="tp-card-desc">{{ t.description }}</div>
            </div>
          </div>
        </div>

        <div class="tp-options">
          <label class="tp-label">
            论文标题
            <input
              v-model="title"
              class="tp-input"
              placeholder="（可选）输入论文标题"
              @keydown.enter="create"
            />
          </label>

          <div class="tp-sections">
            <span class="tp-label">包含章节</span>
            <div class="tp-checks">
              <label v-for="sec in sectionOptions" :key="sec.id" class="tp-check">
                <input type="checkbox" v-model="sec.checked" />
                {{ sec.label }}
              </label>
            </div>
          </div>
        </div>
      </div>

      <div class="tp-footer">
        <span v-if="error" class="tp-error">{{ error }}</span>
        <button class="tp-btn tp-btn-cancel" @click="close">取消</button>
        <button class="tp-btn tp-btn-create" :disabled="!selected || loading" @click="create">
          {{ loading ? '生成中...' : '创建' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'

const isTauri = '__TAURI_INTERNALS__' in window
const API = isTauri ? 'http://localhost:18088' : ''

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'create', markdown: string, templateId: string): void
}>()

const templates = ref<{ id: string; name: string; venue: string; description: string; icon: string }[]>([])
const selected = ref('generic_article')
const title = ref('')
const loading = ref(false)
const error = ref('')

const sectionOptions = reactive([
  { id: 'title', label: '标题', checked: true },
  { id: 'abstract', label: '摘要', checked: true },
  { id: 'introduction', label: '引言', checked: true },
  { id: 'method', label: '方法', checked: true },
  { id: 'experiment', label: '实验', checked: true },
  { id: 'conclusion', label: '结论', checked: true },
])

async function loadTemplates() {
  try {
    error.value = ''
    const resp = await fetch(`${API}/api/paper-assets/templates`)
    if (resp.ok) {
      const data = await resp.json()
      templates.value = data.templates || []
    } else {
      error.value = '后端未响应，请检查 Python 后端是否运行'
    }
  } catch (e) {
    error.value = `加载模板失败: ${e}`
  }
}

function close() {
  emit('close')
}

async function create() {
  if (!selected.value || loading.value) return
  loading.value = true
  error.value = ''
  try {
    const sections = sectionOptions.filter(s => s.checked).map(s => s.id)
    const resp = await fetch(`${API}/api/paper-scaffold`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        template_id: selected.value,
        title: title.value,
        sections,
      }),
    })
    if (resp.ok) {
      const data = await resp.json()
      emit('create', data.markdown, data.template_id)
      close()
    } else {
      const errData = await resp.json().catch(() => ({}))
      error.value = errData.detail || `创建失败 (${resp.status})`
    }
  } catch (e) {
    error.value = `创建失败: ${e}`
  }
  finally {
    loading.value = false
  }
}

import { watch } from 'vue'
watch(() => props.visible, (v) => {
  if (v && templates.value.length === 0) loadTemplates()
})
</script>

<style scoped>
.template-picker-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  backdrop-filter: blur(4px);
}

.template-picker {
  background: var(--surface, #1a1a1e);
  border: 1px solid var(--border-color, #27272a);
  border-radius: 12px;
  width: 640px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}

.tp-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-color, #27272a);
}

.tp-header h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary, #d4d4d4);
  margin: 0;
}

.tp-close {
  background: none;
  border: none;
  color: var(--text-secondary, #888);
  font-size: 20px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 4px;
}
.tp-close:hover { background: var(--hover-bg, #2d2d2d); color: var(--text-primary, #d4d4d4); }

.tp-body {
  padding: 16px 20px;
  overflow-y: auto;
  flex: 1;
}

.tp-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
  margin-bottom: 16px;
}

.tp-card {
  display: flex;
  gap: 12px;
  padding: 12px;
  border: 1px solid var(--border-color, #27272a);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
  background: transparent;
}
.tp-card:hover { border-color: var(--accent, #3b82f6); background: var(--hover-bg, #2d2d2d); }
.tp-card.active { border-color: var(--accent, #3b82f6); background: var(--active-bg, #37373d); box-shadow: 0 0 0 1px var(--accent, #3b82f6); }

.tp-card-icon {
  font-size: 28px;
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.tp-card-info { flex: 1; min-width: 0; }

.tp-card-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary, #d4d4d4);
}

.tp-card-venue {
  font-size: 11px;
  color: var(--accent, #3b82f6);
  margin: 2px 0;
}

.tp-card-desc {
  font-size: 12px;
  color: var(--text-secondary, #888);
  line-height: 1.4;
}

.tp-options {
  border-top: 1px solid var(--border-color, #27272a);
  padding-top: 14px;
}

.tp-label {
  display: block;
  font-size: 12px;
  color: var(--text-secondary, #888);
  margin-bottom: 6px;
}

.tp-input {
  display: block;
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border-color, #27272a);
  border-radius: 6px;
  background: var(--input-bg, #2d2d2d);
  color: var(--text-primary, #d4d4d4);
  font-size: 14px;
  margin-top: 4px;
  outline: none;
}
.tp-input:focus { border-color: var(--accent, #3b82f6); }

.tp-sections { margin-top: 12px; }

.tp-checks {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 6px;
}

.tp-check {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: var(--text-primary, #d4d4d4);
  cursor: pointer;
}
.tp-check input { accent-color: var(--accent, #3b82f6); }

.tp-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 20px;
  border-top: 1px solid var(--border-color, #27272a);
}

.tp-btn {
  padding: 8px 20px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}

.tp-btn-cancel {
  background: transparent;
  color: var(--text-secondary, #888);
  border: 1px solid var(--border-color, #27272a);
}
.tp-btn-cancel:hover { background: var(--hover-bg, #2d2d2d); color: var(--text-primary, #d4d4d4); }

.tp-btn-create {
  background: var(--accent, #3b82f6);
  color: #fff;
}
.tp-btn-create:hover { opacity: 0.9; }
.tp-btn-create:disabled { opacity: 0.5; cursor: not-allowed; }

.tp-error {
  flex: 1;
  font-size: 12px;
  color: #f87171;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
