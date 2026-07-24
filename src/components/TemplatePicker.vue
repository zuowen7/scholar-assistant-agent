<template>
  <AppDialog
    :model-value="visible"
    :title="t('editor.newPaper')"
    :subtitle="t('editor.chooseTemplate')"
    :close-label="t('general.close')"
    :close-on-backdrop="!loading"
    @update:model-value="!$event && !loading && close()"
  >
    <div class="template-body">
      <div v-if="loadingTemplates" class="template-state" role="status">
        <span class="state-spinner" aria-hidden="true" />
        <span>{{ t('general.loading') }}</span>
      </div>
      <template v-else-if="templates.length">
        <div class="template-grid" role="radiogroup" :aria-label="t('project.template')">
          <label
            v-for="template in templates"
            :key="template.id"
            class="template-option"
            :class="{ active: selected === template.id }"
          >
            <input v-model="selected" type="radio" :value="template.id" />
            <span class="template-monogram" aria-hidden="true">{{
              template.icon || template.name.slice(0, 2)
            }}</span>
            <span class="template-copy">
              <strong>{{ template.name }}</strong>
              <small class="template-venue">{{ template.venue }}</small>
              <span>{{ template.description }}</span>
            </span>
            <Check v-if="selected === template.id" :size="17" aria-hidden="true" />
          </label>
        </div>

        <div class="template-options">
          <label class="field">
            <span
              >{{ t('general.title') }} <i>{{ t('general.optional') }}</i></span
            >
            <input
              v-model="title"
              :placeholder="t('editor.paperTitlePlaceholder')"
              @keydown.enter="create"
            />
          </label>
          <fieldset>
            <legend>{{ t('editor.includedSections') }}</legend>
            <div class="section-options">
              <label v-for="section in sectionOptions" :key="section.id">
                <input v-model="section.checked" type="checkbox" />
                <span>{{ sectionLabel(section.id) }}</span>
              </label>
            </div>
          </fieldset>
        </div>
      </template>
      <div v-else class="template-state template-state--error">
        <AlertCircle :size="22" />
        <strong>{{ t('editor.noTemplates') }}</strong>
        <span>{{ error }}</span>
        <UiButton variant="secondary" size="sm" @click="loadTemplates">{{
          t('translate.retry')
        }}</UiButton>
      </div>
      <p v-if="error && templates.length" class="inline-error" role="alert">{{ error }}</p>
    </div>

    <template #footer>
      <UiButton variant="secondary" :disabled="loading" @click="close">{{
        t('general.cancel')
      }}</UiButton>
      <UiButton
        variant="primary"
        :loading="loading"
        :disabled="!selected || loadingTemplates"
        @click="create"
      >
        {{ loading ? t('general.saving') : t('general.create') }}
      </UiButton>
    </template>
  </AppDialog>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { AlertCircle, Check } from 'lucide-vue-next'
import AppDialog from './shell/AppDialog.vue'
import UiButton from './ui/UiButton.vue'
import { API_BASE } from '../utils/api'

const props = defineProps<{ visible: boolean; isDark?: boolean }>()
const { t } = useI18n()
const emit = defineEmits<{ close: []; create: [markdown: string, templateId: string] }>()

const templates = ref<
  { id: string; name: string; venue: string; description: string; icon: string }[]
>([])
const selected = ref('generic_article')
const title = ref('')
const loading = ref(false)
const loadingTemplates = ref(false)
const error = ref('')
const sectionOptions = reactive([
  { id: 'title', checked: true },
  { id: 'abstract', checked: true },
  { id: 'introduction', checked: true },
  { id: 'method', checked: true },
  { id: 'experiment', checked: true },
  { id: 'conclusion', checked: true },
])

function sectionLabel(id: string) {
  const keys: Record<string, string> = {
    title: 'general.title',
    abstract: 'translate.section.abstract',
    introduction: 'translate.section.introduction',
    method: 'translate.section.methods',
    experiment: 'editor.experiment',
    conclusion: 'translate.section.conclusion',
  }
  return t(keys[id] || id)
}

async function loadTemplates() {
  loadingTemplates.value = true
  error.value = ''
  try {
    const resp = await fetch(`${API_BASE}/api/paper-assets/templates`, {
      signal: AbortSignal.timeout(8000),
    })
    if (!resp.ok) throw new Error(t('editor.requestFailed', { msg: resp.status }))
    const data = await resp.json()
    templates.value = data.templates || []
    if (
      templates.value.length &&
      !templates.value.some((template) => template.id === selected.value)
    )
      selected.value = templates.value[0].id
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
    const sections = sectionOptions
      .filter((section) => section.checked)
      .map((section) => section.id)
    const resp = await fetch(`${API_BASE}/api/paper-scaffold`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ template_id: selected.value, title: title.value, sections }),
    })
    if (!resp.ok) {
      const errData = await resp.json().catch(() => ({}))
      throw new Error(errData.detail || t('editor.requestFailed', { msg: resp.status }))
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

watch(
  () => props.visible,
  (visible) => {
    if (visible) void loadTemplates()
  },
)
</script>

<style scoped>
.template-body {
  padding: 22px;
}
.template-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}
.template-option {
  display: grid;
  min-width: 0;
  grid-template-columns: 42px minmax(0, 1fr) 18px;
  align-items: start;
  gap: 11px;
  padding: 12px;
  border: 1px solid var(--c-border);
  border-radius: 9px;
  background: var(--c-panel);
  color: var(--c-text-1);
  cursor: pointer;
}
.template-option:hover {
  background: var(--c-surface-2);
}
.template-option.active {
  border-color: var(--c-accent);
  background: var(--c-accent-bg);
}
.template-option > input {
  position: absolute;
  opacity: 0;
}
.template-option > svg {
  margin-top: 3px;
  color: var(--c-accent);
}
.template-monogram {
  display: grid;
  width: 42px;
  height: 42px;
  place-items: center;
  border-radius: 8px;
  background: var(--c-nav);
  color: var(--c-text-1);
  font: 650 11px/1 var(--font-sans);
}
.template-copy {
  display: grid;
  min-width: 0;
  gap: 3px;
}
.template-copy strong {
  color: var(--c-text-0);
  font-size: 13px;
}
.template-copy small {
  color: var(--c-accent);
  font-size: 10px;
  letter-spacing: 0.03em;
}
.template-copy > span {
  display: -webkit-box;
  overflow: hidden;
  color: var(--c-text-2);
  font-size: 11px;
  line-height: 1.45;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}
.template-options {
  display: grid;
  gap: 20px;
  margin-top: 22px;
  padding-top: 20px;
  border-top: 1px solid var(--c-border);
}
.field {
  display: grid;
  gap: 7px;
  color: var(--c-text-1);
  font-size: 12px;
  font-weight: 600;
}
.field i {
  margin-left: 4px;
  color: var(--c-text-3);
  font-style: normal;
  font-weight: 400;
}
.field input {
  height: 40px;
  padding: 0 11px;
  border: 1px solid var(--c-border);
  border-radius: 8px;
  outline: none;
  background: var(--input-bg);
  color: var(--c-text-0);
  font: inherit;
}
.field input:focus {
  border-color: var(--c-accent);
  box-shadow: var(--ring-focus);
}
fieldset {
  margin: 0;
  padding: 0;
  border: 0;
}
legend {
  margin-bottom: 9px;
  color: var(--c-text-1);
  font-size: 12px;
  font-weight: 600;
}
.section-options {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.section-options label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 10px;
  border: 1px solid var(--c-border);
  border-radius: 7px;
  color: var(--c-text-1);
  font-size: 12px;
  cursor: pointer;
}
.section-options label:has(input:checked) {
  border-color: var(--c-accent);
  background: var(--c-accent-bg);
}
.section-options input {
  accent-color: var(--c-accent);
}
.template-state {
  display: grid;
  min-height: 240px;
  place-items: center;
  align-content: center;
  gap: 10px;
  color: var(--c-text-2);
  font-size: 12px;
  text-align: center;
}
.template-state--error svg {
  color: var(--c-danger);
}
.template-state--error strong {
  color: var(--c-text-0);
  font-size: 14px;
}
.template-state--error > span {
  max-width: 420px;
  overflow-wrap: anywhere;
}
.state-spinner {
  width: 22px;
  height: 22px;
  border: 2px solid var(--c-border);
  border-top-color: var(--c-accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
.inline-error {
  margin: 14px 0 0;
  padding: 10px 12px;
  border-left: 3px solid var(--c-danger);
  background: var(--c-danger-bg);
  color: var(--c-danger-fg);
  font-size: 12px;
}
@keyframes spin {
  to {
    transform: rotate(1turn);
  }
}
@media (max-width: 650px) {
  .template-grid {
    grid-template-columns: 1fr;
  }
  .template-body {
    padding: 18px;
  }
}
</style>
