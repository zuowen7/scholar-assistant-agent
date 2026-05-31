<template>
  <div v-if="visible" class="template-picker-overlay" :class="{ light: !isDark }" @click.self="close">
    <section class="template-picker" role="dialog" aria-modal="true" aria-labelledby="template-title">
      <header class="tp-header">
        <div>
          <h3 id="template-title">{{ t('editor.newProject') }}</h3>
          <p>{{ t('editor.chooseTemplate') }}</p>
        </div>
        <button class="tp-close" @click="close" :title="t('general.close')">×</button>
      </header>

      <div class="tp-body">
        <div v-if="loadingTemplates" class="tp-state">{{ t('general.loading') }}</div>
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
        <div v-else class="tp-state">{{ t('editor.noTemplates') }}</div>

        <div class="tp-options">
          <label class="tp-label">
            {{ t('general.title') }}
            <input
              v-model="title"
              class="tp-input"
              :placeholder="t('general.optional') + ' ' + t('general.title')"
              @keydown.enter="create"
            />
          </label>

          <div class="tp-sections">
            <span class="tp-label">{{ t('editor.includedSections') }}</span>
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
        <button v-if="error" class="tp-btn tp-btn-ghost" @click="loadTemplates">{{ t('translate.retry') }}</button>
        <button class="tp-btn tp-btn-cancel" @click="close">{{ t('general.cancel') }}</button>
        <button class="tp-btn tp-btn-create" :disabled="!selected || loading" @click="create">
          {{ loading ? t('general.saving') : t('general.create') }}
        </button>
      </footer>
    </section>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { API_BASE } from '../utils/api'

const props = defineProps<{ visible: boolean; isDark?: boolean }>()
const isDark = props.isDark !== undefined ? props.isDark : true
const { t } = useI18n()

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
  { id: 'title', label: t('general.title'), checked: true },
  { id: 'abstract', label: t('translate.section.abstract'), checked: true },
  { id: 'introduction', label: t('translate.section.introduction'), checked: true },
  { id: 'method', label: t('translate.section.methods'), checked: true },
  { id: 'experiment', label: t('editor.experiment'), checked: true },
  { id: 'conclusion', label: t('translate.section.conclusion'), checked: true },
])

async function loadTemplates() {
  loadingTemplates.value = true
  error.value = ''
  try {
    const resp = await fetch(`${API_BASE}/api/paper-assets/templates`, {
      signal: AbortSignal.timeout(8000),
    })
    if (!resp.ok) {
      error.value = t('editor.requestFailed', { msg: resp.status })
      return
    }
    const data = await resp.json()
    templates.value = data.templates || []
    if (templates.value.length && !templates.value.some(t => t.id === selected.value)) {
      selected.value = templates.value[0].id
    }
  } catch (e) {
    error.value = t('editor.requestFailed', { msg: e instanceof Error ? e.message : String(e) })
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
      error.value = errData.detail || t('editor.requestFailed', { msg: resp.status })
      return
    }
    const data = await resp.json()
    emit('create', data.markdown, data.template_id)
    close()
  } catch (e) {
    error.value = t('editor.requestFailed', { msg: e instanceof Error ? e.message : String(e) })
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
  background: var(--c-overlay);
  backdrop-filter: blur(8px);
}

.template-picker {
  width: min(760px, 100%);
  max-height: min(760px, 88vh);
  display: flex;
  flex-direction: column;
  background: var(--c-surface-1);
  color: var(--text-primary);
  border: 1px solid var(--c-surface-3);
  border-radius: 10px;
  box-shadow: 0 28px 80px var(--c-shadow);
  overflow: hidden;
}

.tp-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 20px;
  border-bottom: 1px solid var(--c-surface-3);
}

.tp-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 650;
  color: var(--c-text-0);
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
  border: 1px solid var(--c-surface-3);
  border-radius: 8px;
  background: var(--c-surface-2);
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s, transform 0.15s;
}
.tp-card:hover { border-color: var(--c-accent); background: var(--hover-bg); }
.tp-card.active {
  border-color: var(--c-accent);
  background: var(--c-accent-bg);
  box-shadow: inset 0 0 0 1px var(--c-accent);
}

.tp-card-icon {
  min-width: 44px;
  height: 44px;
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--c-accent-bg);
  color: var(--c-accent-hover);
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
.tp-card-venue { font-size: 11px; color: var(--c-accent-hover); }
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
  border-top: 1px solid var(--c-surface-3);
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
  border: 1px solid var(--c-surface-3);
  border-radius: 7px;
  background: var(--input-bg);
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
}
.tp-input:focus { border-color: var(--c-accent); }

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
.tp-check input { accent-color: var(--c-accent); }

.tp-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  padding: 14px 20px;
  border-top: 1px solid var(--c-surface-3);
}

.tp-error {
  flex: 1;
  min-width: 0;
  color: var(--c-danger);
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tp-btn {
  height: 32px;
  padding: 0 16px;
  border-radius: 7px;
  border: 1px solid var(--c-surface-3);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  background: transparent;
  color: var(--text-primary);
}
.tp-btn:hover { background: var(--hover-bg); }
.tp-btn-create {
  border-color: var(--c-accent);
  background: var(--c-accent);
  color: #fff;
}
.tp-btn-create:hover { opacity: 0.9; }
.tp-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.tp-btn-ghost { color: var(--c-accent-hover); }

@media (max-width: 720px) {
  .tp-grid { grid-template-columns: 1fr; }
}
</style>
