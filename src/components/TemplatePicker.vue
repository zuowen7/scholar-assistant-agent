<template>
  <div v-if="visible" class="template-picker-overlay" :class="{ light: !isDark }" @click.self="close">
    <section class="template-picker" role="dialog" aria-modal="true" aria-labelledby="template-title">
      <header class="tp-header">
        <div>
          <h3 id="template-title">新建论文</h3>
          <p>选择一个论文结构模板，生成可继续编辑的 Markdown 草稿。</p>
        </div>
        <button class="tp-close" @click="close" title="关闭">×</button>
      </header>

      <div class="tp-body">
        <div v-if="loadingTemplates" class="tp-state">正在加载模板...</div>
        <div v-else-if="templates.length" class="tp-grid">
          <button
            v-for="t in templates"
            :key="t.id"
            type="button"
            class="tp-card"
            :class="{ active: selected === t.id }"
            @click="selected = t.id"
          >
            <span class="tp-card-icon">{{ t.icon }}</span>
            <span class="tp-card-info">
              <span class="tp-card-name">{{ t.name }}</span>
              <span class="tp-card-venue">{{ t.venue }}</span>
              <span class="tp-card-desc">{{ t.description }}</span>
            </span>
          </button>
        </div>
        <div v-else class="tp-state">还没有可用模板</div>

        <div class="tp-options">
          <label class="tp-label">
            论文标题
            <input
              v-model="title"
              class="tp-input"
              placeholder="可选，输入论文标题"
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

      <footer class="tp-footer">
        <span v-if="error" class="tp-error">{{ error }}</span>
        <button v-if="error" class="tp-btn tp-btn-ghost" @click="loadTemplates">重试</button>
        <button class="tp-btn tp-btn-cancel" @click="close">取消</button>
        <button class="tp-btn tp-btn-create" :disabled="!selected || loading" @click="create">
          {{ loading ? '生成中...' : '创建' }}
        </button>
      </footer>
    </section>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { API_BASE } from '../utils/api'

const props = defineProps<{ visible: boolean; isDark?: boolean }>()
const isDark = props.isDark !== undefined ? props.isDark : true
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'create', markdown: string, templateId: string): void
}>()

const templates = ref<{ id: string; name: string; venue: string; description: string; icon: string }[]>([])
const selected = ref('generic_article')
const title = ref('')
const loading = ref(false)
const loadingTemplates = ref(false)
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
  loadingTemplates.value = true
  error.value = ''
  try {
    const resp = await fetch(`${API_BASE}/api/paper-assets/templates`, {
      signal: AbortSignal.timeout(8000),
    })
    if (!resp.ok) {
      error.value = `模板接口异常 (${resp.status})`
      return
    }
    const data = await resp.json()
    templates.value = data.templates || []
    if (templates.value.length && !templates.value.some(t => t.id === selected.value)) {
      selected.value = templates.value[0].id
    }
  } catch (e) {
    error.value = `加载模板失败: ${e instanceof Error ? e.message : String(e)}`
  } finally {
    loadingTemplates.value = false
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
    const resp = await fetch(`${API_BASE}/api/paper-scaffold`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        template_id: selected.value,
        title: title.value,
        sections,
      }),
    })
    if (!resp.ok) {
      const errData = await resp.json().catch(() => ({}))
      error.value = errData.detail || `创建失败 (${resp.status})`
      return
    }
    const data = await resp.json()
    emit('create', data.markdown, data.template_id)
    close()
  } catch (e) {
    error.value = `创建失败: ${e instanceof Error ? e.message : String(e)}`
  } finally {
    loading.value = false
  }
}

watch(() => props.visible, (v) => {
  if (v) loadTemplates()
})
</script>

<style scoped>
.template-picker-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: var(--overlay-bg);
  backdrop-filter: blur(8px);
}

.template-picker {
  width: min(760px, 100%);
  max-height: min(760px, 88vh);
  display: flex;
  flex-direction: column;
  background: var(--surface);
  color: var(--text-primary);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: 0 28px 80px var(--shadow);
  overflow: hidden;
}

.tp-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 20px;
  border-bottom: 1px solid var(--border);
}

.tp-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 650;
  color: var(--text);
}

.tp-header p {
  margin: 5px 0 0;
  color: var(--text-secondary);
  font-size: 12px;
}

.tp-close {
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 20px;
  line-height: 1;
}
.tp-close:hover { background: var(--hover-bg); color: var(--text-primary); }

.tp-body {
  flex: 1;
  overflow-y: auto;
  padding: 18px 20px;
}

.tp-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 18px;
}

.tp-card {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  width: 100%;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface2);
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s, transform 0.15s;
}
.tp-card:hover { border-color: var(--accent); background: var(--hover-bg); }
.tp-card.active {
  border-color: var(--accent);
  background: var(--accent-bg);
  box-shadow: inset 0 0 0 1px var(--accent);
}

.tp-card-icon {
  min-width: 44px;
  height: 44px;
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--accent-bg);
  color: var(--accent2);
  font-size: 12px;
  font-weight: 700;
}

.tp-card-info {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.tp-card-name { font-size: 13px; font-weight: 650; color: var(--text-primary); }
.tp-card-venue { font-size: 11px; color: var(--accent2); }
.tp-card-desc {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.45;
}

.tp-state {
  padding: 24px;
  color: var(--text-secondary);
  text-align: center;
}

.tp-options {
  border-top: 1px solid var(--border);
  padding-top: 16px;
}

.tp-label {
  display: block;
  margin-bottom: 7px;
  color: var(--text-secondary);
  font-size: 12px;
}

.tp-input {
  box-sizing: border-box;
  display: block;
  width: 100%;
  margin-top: 6px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--input-bg);
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
}
.tp-input:focus { border-color: var(--accent); }

.tp-sections { margin-top: 14px; }
.tp-checks {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 14px;
  margin-top: 8px;
}

.tp-check {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
}
.tp-check input { accent-color: var(--accent); }

.tp-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  padding: 14px 20px;
  border-top: 1px solid var(--border);
}

.tp-error {
  flex: 1;
  min-width: 0;
  color: var(--red);
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tp-btn {
  height: 32px;
  padding: 0 16px;
  border-radius: 7px;
  border: 1px solid var(--border);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  background: transparent;
  color: var(--text-primary);
}
.tp-btn:hover { background: var(--hover-bg); }
.tp-btn-create {
  border-color: var(--accent);
  background: var(--accent);
  color: #fff;
}
.tp-btn-create:hover { opacity: 0.9; }
.tp-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.tp-btn-ghost { color: var(--accent2); }

@media (max-width: 720px) {
  .tp-grid { grid-template-columns: 1fr; }
}
</style>
