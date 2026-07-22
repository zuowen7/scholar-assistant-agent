<template>
  <AppDialog
    :model-value="visible"
    :title="t('project.create')"
    :subtitle="t('project.createDescription')"
    :close-label="t('general.close')"
    :close-on-backdrop="!creating"
    @update:model-value="!$event && !creating && $emit('close')"
  >
    <form class="project-form" @submit.prevent="handleCreate">
      <div class="field-grid">
        <label class="field">
          <span>{{ t('project.name') }} <i>{{ t('general.required') }}</i></span>
          <input v-model="form.name" data-test="project-name" autofocus :placeholder="t('project.namePlaceholder')" maxlength="200" />
        </label>
        <label class="field">
          <span>{{ t('project.author') }}</span>
          <input v-model="form.author" :placeholder="t('project.authorPlaceholder')" maxlength="200" />
        </label>
      </div>

      <fieldset class="template-fieldset">
        <legend>{{ t('project.template') }}</legend>
        <div v-if="templatesLoading" class="template-state" role="status">{{ t('general.loading') }}</div>
        <div v-else-if="templates.length" class="template-grid">
          <label v-for="tpl in templates" :key="tpl.id" data-test="template-option" class="template-card" :class="{ active: form.templateId === tpl.id }" @click="form.templateId = tpl.id">
            <input v-model="form.templateId" type="radio" :value="tpl.id" />
            <span class="template-check" aria-hidden="true" />
            <span class="template-copy">
              <strong>{{ tpl.name }}</strong>
              <small>{{ templateDescription(tpl) }}</small>
            </span>
          </label>
        </div>
        <div v-else class="template-state template-state--error">
          <span>{{ templateError || t('editor.noTemplates') }}</span>
          <UiButton type="button" variant="secondary" size="sm" @click="loadTemplates">{{ t('translate.retry') }}</UiButton>
        </div>
      </fieldset>

      <label class="field">
        <span>{{ t('project.location') }} <i>{{ t('general.required') }}</i></span>
        <div class="location-row">
          <input v-model="form.location" data-test="project-location" spellcheck="false" :placeholder="t('project.locationPlaceholder')" />
          <UiButton data-test="browse-btn" type="button" variant="secondary" @click="browseLocation"><FolderOpen :size="15" />{{ t('project.browse') }}</UiButton>
        </div>
      </label>

      <label class="git-row">
        <input v-model="form.initGit" data-test="git-checkbox" type="checkbox" />
        <span><strong>{{ t('project.initGit') }}</strong><small>{{ t('project.initGitDescription') }}</small></span>
      </label>

      <p v-if="error" class="form-error" role="alert"><AlertCircle :size="16" />{{ error }}</p>
    </form>

    <template #footer>
      <UiButton variant="secondary" :disabled="creating" @click="$emit('close')">{{ t('general.cancel') }}</UiButton>
      <UiButton data-test="create-btn" variant="primary" :loading="creating" :disabled="!canCreate" @click="handleCreate">
        {{ creating ? t('project.creating') : t('project.create') }}
      </UiButton>
    </template>
  </AppDialog>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { AlertCircle, FolderOpen } from 'lucide-vue-next'
import AppDialog from './shell/AppDialog.vue'
import UiButton from './ui/UiButton.vue'
import { useProject } from '../composables/useProject'
import { API_BASE } from '../utils/api'
import type { ProjectTemplate } from '../types'
import { open as openDialog } from '@tauri-apps/plugin-dialog'

const { t } = useI18n()
const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{ close: []; 'project-created': [path: string] }>()
const { createProject } = useProject()

const form = reactive({ name: '', author: '', templateId: 'research_paper', location: '', initGit: true })
const templates = ref<ProjectTemplate[]>([])
const templatesLoading = ref(false)
const templateError = ref('')
const creating = ref(false)
const error = ref('')
const canCreate = computed(() => !!form.name.trim() && !!form.location && !creating.value && !templatesLoading.value)

function templateDescription(template: ProjectTemplate) {
  const candidate = template as ProjectTemplate & { description?: string; venue?: string }
  return candidate.description || candidate.venue || t('project.templateReady')
}

async function loadTemplates() {
  templatesLoading.value = true
  templateError.value = ''
  try {
    const resp = await fetch(`${API_BASE}/api/project/templates`, { signal: AbortSignal.timeout(8000) })
    if (!resp.ok) throw new Error(t('editor.requestFailed', { msg: resp.status }))
    templates.value = await resp.json()
    if (templates.value.length && !templates.value.some(template => template.id === form.templateId)) form.templateId = templates.value[0].id
  } catch (e) {
    templates.value = []
    templateError.value = e instanceof Error ? e.message : t('project.createFailed')
  } finally {
    templatesLoading.value = false
  }
}

onMounted(loadTemplates)
watch(() => props.visible, visible => { if (visible && !templates.value.length) void loadTemplates() })

async function browseLocation() {
  try {
    const selected = await openDialog({ directory: true, multiple: false })
    if (typeof selected === 'string') form.location = selected
  } catch { /* cancellation is not an error */ }
}

async function handleCreate() {
  if (!canCreate.value) return
  creating.value = true
  error.value = ''
  try {
    const result = await createProject({ name: form.name.trim(), location: form.location, author: form.author, template_id: form.templateId, init_git: form.initGit })
    form.name = ''
    form.author = ''
    form.templateId = 'research_paper'
    form.location = ''
    form.initGit = true
    emit('project-created', result.project_path)
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('project.createFailed')
  } finally {
    creating.value = false
  }
}
</script>

<style scoped>
.project-form { display: grid; gap: 22px; padding: 24px; }
.field-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.field { display: grid; gap: 7px; color: var(--c-text-1); font-size: 12px; }
.field > span, legend { font-weight: 600; }
.field i { margin-left: 3px; color: var(--brand-red); font-style: normal; font-weight: 400; }
.field input { width: 100%; height: 40px; box-sizing: border-box; padding: 0 11px; border: 1px solid var(--c-border); border-radius: 8px; outline: none; background: var(--input-bg); color: var(--c-text-0); font: inherit; font-size: 13px; }
.field input:focus { border-color: var(--c-accent); box-shadow: var(--ring-focus); }
.template-fieldset { min-width: 0; margin: 0; padding: 0; border: 0; }
legend { margin-bottom: 9px; color: var(--c-text-1); font-size: 12px; }
.template-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.template-card { display: flex; min-width: 0; align-items: flex-start; gap: 10px; padding: 12px; border: 1px solid var(--c-border); border-radius: 9px; background: var(--c-panel); cursor: pointer; }
.template-card:hover { background: var(--c-surface-2); }
.template-card.active { border-color: var(--c-accent); background: var(--c-accent-bg); }
.template-card input { position: absolute; opacity: 0; pointer-events: none; }
.template-check { width: 14px; height: 14px; flex: 0 0 auto; margin-top: 2px; border: 1px solid var(--c-border); border-radius: 50%; background: var(--c-panel); box-shadow: inset 0 0 0 3px var(--c-panel); }
.template-card.active .template-check { border-color: var(--c-accent); background: var(--c-accent); }
.template-copy { display: grid; min-width: 0; gap: 4px; }
.template-copy strong { overflow: hidden; color: var(--c-text-0); font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }
.template-copy small { display: -webkit-box; overflow: hidden; color: var(--c-text-2); font-size: 11px; line-height: 1.45; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.template-state { display: flex; min-height: 82px; align-items: center; justify-content: center; gap: 10px; border: 1px dashed var(--c-border); border-radius: 9px; color: var(--c-text-2); font-size: 12px; }
.template-state--error { flex-direction: column; color: var(--c-danger-fg); }
.location-row { display: flex; gap: 8px; }
.location-row input { min-width: 0; flex: 1; }
.git-row { display: flex; align-items: flex-start; gap: 10px; padding: 13px; border-radius: 9px; background: var(--c-surface-2); color: var(--c-text-1); cursor: pointer; }
.git-row input { margin-top: 2px; accent-color: var(--c-accent); }
.git-row span { display: grid; gap: 3px; }
.git-row strong { font-size: 12px; }
.git-row small { color: var(--c-text-2); font-size: 11px; line-height: 1.45; }
.form-error { display: flex; align-items: flex-start; gap: 8px; margin: 0; padding: 10px 12px; border-left: 3px solid var(--c-danger); background: var(--c-danger-bg); color: var(--c-danger-fg); font-size: 12px; line-height: 1.5; }
.form-error svg { flex: 0 0 auto; }
@media (max-width: 620px) { .field-grid, .template-grid { grid-template-columns: 1fr; } .project-form { padding: 20px 18px; } }
</style>
