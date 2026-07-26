<template>
  <div class="source-library">
    <AppHeader
      v-if="surface === 'library'"
      :title="t('sources.title')"
      :subtitle="t('sources.subtitle', { count: library.sources.value.length })"
      :icon="Library"
    >
      <UiButton variant="secondary" size="sm" @click="pickReference">
        {{ t('sources.addOnly') }}
      </UiButton>
      <UiButton variant="primary" size="sm" @click="surface = 'translation'">
        {{ t('sources.translateAndAdd') }}
      </UiButton>
    </AppHeader>

    <template v-if="surface === 'library'">
      <div class="library-toolbar">
        <UiSegmented v-model="filter" :options="filterOptions" size="sm" />
        <span v-if="library.loading.value">{{ t('general.loading') }}</span>
        <span v-else-if="library.error.value" class="library-error">{{ library.error.value }}</span>
      </div>

      <div v-if="filteredSources.length" class="source-list">
        <article v-for="source in filteredSources" :key="source.id" class="source-card">
          <div class="source-icon"><FileText :size="19" /></div>
          <div class="source-copy">
            <strong>{{ source.title }}</strong>
            <span>
              {{ source.translation_task_id ? t('sources.translated') : t('sources.originalOnly') }}
              · {{ ragLabel(source.rag_status) }}
            </span>
          </div>
          <button
            type="button"
            class="status-action"
            @click="
              library.updateSource(source, {
                reading_status: source.reading_status === 'read' ? 'unread' : 'read',
              })
            "
          >
            {{ source.reading_status === 'read' ? t('sources.markUnread') : t('sources.markRead') }}
          </button>
          <button
            type="button"
            class="status-action"
            :class="{ active: source.cited }"
            @click="library.updateSource(source, { cited: !source.cited })"
          >
            {{ source.cited ? t('sources.cited') : t('sources.markCited') }}
          </button>
        </article>
      </div>
      <EmptyState
        v-else-if="!library.loading.value"
        :title="t('sources.emptyTitle')"
        :description="t('sources.emptyDescription')"
      >
        <UiButton variant="primary" size="sm" @click="surface = 'translation'">
          {{ t('sources.translateAndAdd') }}
        </UiButton>
      </EmptyState>
    </template>

    <template v-else>
      <div class="translation-context">
        <button type="button" @click="returnToLibrary">
          <ArrowLeft :size="15" /> {{ t('sources.backToLibrary') }}
        </button>
        <span>{{ t('sources.backgroundHint') }}</span>
        <UiButton
          v-if="translationState.status === 'done' && !translationAttached"
          variant="primary"
          size="sm"
          :loading="library.saving.value"
          @click="attachTranslation"
        >
          {{ t('sources.addCurrentTranslation') }}
        </UiButton>
        <span v-else-if="translationAttached" class="attached-state">
          <Check :size="14" /> {{ t('sources.added') }}
        </span>
      </div>
      <TranslateView
        :health-ok="healthOk"
        :backend-restarting="backendRestarting"
        :read-settings="readSettings"
        @restart-backend="$emit('restart-backend')"
        @open-agent-docs="$emit('open-agent-docs')"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ArrowLeft, Check, FileText, Library } from 'lucide-vue-next'
import { open as openDialog } from '@tauri-apps/plugin-dialog'
import { useI18n } from 'vue-i18n'
import AppHeader from './shell/AppHeader.vue'
import EmptyState from './shell/EmptyState.vue'
import TranslateView from './TranslateView.vue'
import UiButton from './ui/UiButton.vue'
import UiSegmented from './ui/UiSegmented.vue'
import { useSourceLibrary, type SourceRagStatus } from '../composables/useSourceLibrary'
import { useTranslate } from '../composables/useTranslate'
import { useToast } from '../composables/useToast'

defineProps<{
  healthOk: boolean
  backendRestarting: boolean
  readSettings: { fontSize: number; lineHeight: number; fontFamily: string; transColor: string }
}>()
defineEmits<{ (event: 'restart-backend'): void; (event: 'open-agent-docs'): void }>()

const { t } = useI18n()
const { pushError, success } = useToast()
const library = useSourceLibrary()
const { state: translationState } = useTranslate()
const surface = ref<'library' | 'translation'>('library')
const filter = ref<'all' | 'unread' | 'translated' | 'cited'>('all')
const translationAttached = ref(false)
const attachedSourceId = ref('')

const filterOptions = computed(() => [
  { value: 'all' as const, label: t('general.all') },
  { value: 'unread' as const, label: t('sources.unread') },
  { value: 'translated' as const, label: t('sources.translated') },
  { value: 'cited' as const, label: t('sources.cited') },
])
const filteredSources = computed(() => {
  if (filter.value === 'unread')
    return library.sources.value.filter((source) => source.reading_status !== 'read')
  if (filter.value === 'translated')
    return library.sources.value.filter((source) => source.translation_task_id)
  if (filter.value === 'cited') return library.sources.value.filter((source) => source.cited)
  return library.sources.value
})

onMounted(() => void library.loadSources().catch(() => undefined))

watch(
  () => translationState.ragStatus,
  async (status) => {
    if (!attachedSourceId.value) return
    const source = library.sources.value.find((item) => item.id === attachedSourceId.value)
    if (!source || source.rag_status === status) return
    await library.updateSource(source, { rag_status: status }).catch(() => undefined)
  },
)

function ragLabel(status: SourceRagStatus) {
  return t(`sources.rag.${status}`)
}

function returnToLibrary() {
  surface.value = 'library'
  void library.loadSources().catch(() => undefined)
}

async function attachTranslation() {
  try {
    const source = await library.attachCurrentTranslation()
    attachedSourceId.value = source.id
    translationAttached.value = true
    success(t('sources.added'))
  } catch (error) {
    pushError(error instanceof Error ? error.message : t('sources.addFailed'))
  }
}

async function pickReference() {
  try {
    const selected = await openDialog({
      multiple: false,
      filters: [{ name: 'Academic documents', extensions: ['pdf', 'docx', 'md', 'txt', 'tex'] }],
    })
    if (typeof selected === 'string') {
      await library.addPathReference(selected)
      success(t('sources.added'))
      return
    }
    if (selected === null) return
  } catch {
    // Browser preview falls back to a standard file picker below.
  }
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.pdf,.docx,.md,.txt,.tex'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    try {
      await library.addLocalReference(file)
      success(t('sources.added'))
    } catch (error) {
      pushError(error instanceof Error ? error.message : t('sources.addFailed'))
    }
  }
  input.click()
}
</script>

<style scoped>
.source-library {
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--c-app-bg);
}
.library-toolbar,
.translation-context {
  flex: 0 0 auto;
  min-height: 48px;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 7px 20px;
  border-bottom: 1px solid var(--c-border);
  background: var(--c-panel);
  color: var(--c-text-3);
  font-size: 12px;
}
.translation-context > button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 0;
  background: transparent;
  color: var(--c-text-1);
  cursor: pointer;
}
.translation-context > span {
  margin-right: auto;
}
.source-list {
  min-height: 0;
  overflow: auto;
  display: grid;
  align-content: start;
  gap: 10px;
  padding: 20px;
}
.source-card {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 12px;
  padding: 15px 16px;
  border: 1px solid var(--c-border);
  border-radius: 10px;
  background: var(--c-panel);
}
.source-icon {
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  border-radius: 9px;
  background: var(--c-accent-soft);
  color: var(--c-accent);
}
.source-copy {
  min-width: 0;
  display: grid;
  gap: 4px;
}
.source-copy strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--c-text-0);
  font-size: 14px;
}
.source-copy span {
  color: var(--c-text-3);
  font-size: 11px;
}
.status-action {
  height: 30px;
  padding: 0 10px;
  border: 1px solid var(--c-border);
  border-radius: 7px;
  background: var(--c-surface-1);
  color: var(--c-text-2);
  cursor: pointer;
}
.status-action:hover,
.status-action.active {
  border-color: var(--c-accent-ring);
  color: var(--c-accent);
  background: var(--c-accent-soft);
}
.library-error {
  color: var(--c-danger);
}
.attached-state {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--c-success);
}
@media (max-width: 780px) {
  .source-card {
    grid-template-columns: auto minmax(0, 1fr);
  }
  .status-action {
    grid-column: span 1;
  }
}
</style>
