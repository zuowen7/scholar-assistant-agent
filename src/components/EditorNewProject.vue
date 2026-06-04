<template>
  <Transition name="v-fade">
    <div v-if="visible" class="project-start-backdrop" @click.self="$emit('close')">
      <Transition name="v-scale-in" appear>
        <div v-if="visible" class="project-start-dialog">
          <div class="project-start-header">
            <div>
              <div class="welcome-kicker">{{ t('project.create') }}</div>
              <h3>{{ t('project.create') }}</h3>
            </div>
            <button class="project-start-close" :aria-label="t('general.close')" @click="$emit('close')">
              <X :size="18" :stroke-width="2" />
            </button>
          </div>

          <div class="project-start-body">
            <!-- Project name -->
            <label class="field-label">{{ t('project.name') }}</label>
            <input
              v-model="form.name"
              data-test="project-name"
              class="field-input"
              :placeholder="t('project.namePlaceholder')"
              maxlength="200"
            />

            <!-- Author -->
            <label class="field-label">{{ t('project.author') }}</label>
            <input
              v-model="form.author"
              class="field-input"
              :placeholder="t('project.authorPlaceholder')"
              maxlength="200"
            />

            <!-- Template -->
            <label class="field-label">{{ t('project.template') }}</label>
            <div class="template-grid">
              <button
                v-for="tpl in templates"
                :key="tpl.id"
                data-test="template-option"
                class="template-card"
                :class="{ active: form.templateId === tpl.id }"
                @click="form.templateId = tpl.id"
              >
                <span class="template-name">{{ tpl.name }}</span>
                <span class="template-folders">{{ tpl.folders.length }} folders</span>
              </button>
            </div>

            <!-- Location -->
            <label class="field-label">{{ t('project.location') }}</label>
            <div class="location-row">
              <input
                v-model="form.location"
                data-test="project-location"
                class="field-input location-input"
                :placeholder="t('project.locationPlaceholder')"
              />
              <button data-test="browse-btn" class="browse-btn u-interactive" @click="browseLocation">
                {{ t('project.browse') }}
              </button>
            </div>

            <!-- Git init -->
            <label class="checkbox-row">
              <input v-model="form.initGit" data-test="git-checkbox" type="checkbox" />
              <span>{{ t('project.initGit') }}</span>
            </label>

            <!-- Error message -->
            <div v-if="error" class="error-msg">{{ error }}</div>

            <!-- Create button -->
            <button
              data-test="create-btn"
              class="create-btn u-interactive"
              :disabled="!form.name.trim() || !form.location || creating"
              @click="handleCreate"
            >
              {{ creating ? t('project.creating') : t('project.create') }}
            </button>
          </div>
        </div>
      </Transition>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { X } from './ui/icons'
import { useProject } from '../composables/useProject'
import { API_BASE } from '../utils/api'
import type { ProjectTemplate } from '../types'

const { t } = useI18n()

defineProps<{ visible: boolean }>()

const emit = defineEmits<{
  close: []
  'project-created': [path: string]
}>()

const { createProject } = useProject()

const form = reactive({
  name: '',
  author: '',
  templateId: 'research_paper',
  location: '',
  initGit: true,
})

const templates = ref<ProjectTemplate[]>([])
const creating = ref(false)
const error = ref('')

onMounted(async () => {
  try {
    const resp = await fetch(`${API_BASE}/api/project/templates`)
    if (resp.ok) templates.value = await resp.json()
  } catch { /* use empty list */ }
})

async function browseLocation() {
  try {
    const { open } = await import('@tauri-apps/plugin-dialog')
    const selected = await open({ directory: true, multiple: false })
    if (typeof selected === 'string') form.location = selected
  } catch { /* user cancelled */ }
}

async function handleCreate() {
  if (!form.name.trim() || !form.location) return
  creating.value = true
  error.value = ''
  try {
    const result = await createProject({
      name: form.name.trim(),
      location: form.location,
      author: form.author,
      template_id: form.templateId,
      init_git: form.initGit,
    })
    // Reset form after success
    form.name = ''
    form.author = ''
    form.templateId = 'research_paper'
    form.location = ''
    form.initGit = true
    emit('project-created', result.project_path)
  } catch (e: any) {
    error.value = e.message || t('project.createFailed')
  } finally {
    creating.value = false
  }
}
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
  width: min(560px, calc(100vw - 48px));
  max-height: 85vh;
  border: 1px solid var(--c-surface-3);
  border-radius: var(--radius-lg);
  background: var(--c-surface-2);
  color: var(--c-text-1);
  box-shadow: var(--elevation-4);
  overflow-y: auto;
}

.project-start-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  padding: 18px 20px;
  border-bottom: 1px solid var(--c-surface-3);
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
  transition: color var(--motion-fast), background var(--motion-fast), transform var(--motion-fast) var(--ease-spring);
}
.project-start-close:hover { color: var(--c-text-0); background: var(--c-surface-4); transform: rotate(90deg); }
.project-start-close:active { transform: scale(0.85); }

.project-start-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 18px 20px 20px;
}

.field-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--c-text-2);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.field-input {
  height: 36px;
  border: 1px solid var(--c-surface-3);
  border-radius: var(--radius-sm);
  background: var(--c-surface-0);
  color: var(--c-text-1);
  padding: 0 10px;
  font: inherit;
  font-size: 13px;
  outline: none;
  transition: border-color var(--motion-fast) var(--ease-out);
}
.field-input:focus { border-color: var(--c-accent); box-shadow: var(--ring-focus); }

.template-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.template-card {
  border: 1px solid var(--c-surface-3);
  border-radius: var(--radius-md);
  background: var(--c-surface-1);
  color: var(--c-text-1);
  padding: 10px 12px;
  cursor: pointer;
  text-align: left;
  font: inherit;
  transition: border-color var(--motion-fast), background var(--motion-fast);
}
.template-card:hover { border-color: var(--c-accent); background: var(--c-surface-3); }
.template-card.active {
  border-color: var(--c-accent);
  background: color-mix(in srgb, var(--c-accent) 15%, var(--c-surface-1));
}
.template-name { display: block; font-size: 13px; font-weight: 600; }
.template-folders { font-size: 11px; color: var(--c-text-3); }

.location-row { display: flex; gap: 8px; }
.location-input { flex: 1; }

.browse-btn {
  height: 36px;
  border: 1px solid var(--c-surface-4);
  border-radius: var(--radius-sm);
  background: var(--c-surface-3);
  color: var(--c-text-1);
  padding: 0 14px;
  font: inherit;
  font-size: 13px;
  cursor: pointer;
  white-space: nowrap;
}
.browse-btn:hover { background: var(--c-surface-4); }

.checkbox-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  cursor: pointer;
}
.checkbox-row input { accent-color: var(--c-accent); }

.error-msg {
  font-size: 12px;
  color: var(--c-danger);
  padding: 8px 10px;
  background: color-mix(in srgb, var(--c-danger) 10%, transparent);
  border-radius: var(--radius-sm);
}

.create-btn {
  height: 40px;
  border: 1px solid var(--c-accent);
  border-radius: var(--radius-md);
  background: var(--c-accent);
  color: var(--c-surface-0);
  font: inherit;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: background var(--motion-fast), opacity var(--motion-fast);
}
.create-btn:hover:not(:disabled) { background: var(--c-accent-hover); }
.create-btn:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
