<template>
  <div class="export-workspace">
    <AppHeader
      :title="t('exports.title')"
      :subtitle="t('exports.subtitle', { document: activeTab?.name || t('exports.noDocument') })"
      :icon="PackageCheck"
    >
      <UiButton
        variant="secondary"
        size="sm"
        :disabled="!activeTab"
        @click="exports.generatePreview"
      >
        {{ t('exports.generatePreview') }}
      </UiButton>
      <UiButton
        variant="primary"
        size="sm"
        :disabled="!activeTab || exports.blockingIssues.value.length > 0"
        :loading="exports.loading.value"
        @click="runExport"
      >
        {{ t('exports.exportAction') }}
      </UiButton>
    </AppHeader>

    <EmptyState
      v-if="!activeTab"
      :title="t('exports.noDocument')"
      :description="t('exports.noDocumentDescription')"
    >
      <UiButton variant="primary" size="sm" @click="workspace.navigate('draft')">
        {{ t('exports.backToDraft') }}
      </UiButton>
    </EmptyState>

    <div v-else class="export-grid">
      <aside class="export-settings">
        <section>
          <p class="section-kicker">{{ t('exports.outputFormat') }}</p>
          <UiSegmented v-model="exports.format.value" :options="formatOptions" size="sm" />
        </section>
        <section>
          <label for="export-template">{{ t('exports.targetTemplate') }}</label>
          <select
            id="export-template"
            v-model="exports.templateId.value"
            :disabled="exports.format.value === 'word'"
          >
            <option
              v-for="template in exports.templates.value"
              :key="template.id"
              :value="template.id"
            >
              {{ template.name }}
            </option>
          </select>
          <span v-if="exports.format.value === 'word'">{{ t('exports.wordTemplateHint') }}</span>
          <span
            v-else-if="exports.format.value === 'pdf' && !exports.tectonicAvailable.value"
            class="warn"
          >
            {{ t('exports.compilerUnavailable') }}
          </span>
        </section>
        <section class="document-context">
          <p class="section-kicker">{{ t('exports.documentContext') }}</p>
          <strong>{{ exports.title.value }}</strong>
          <span>{{ activeTab.name }}</span>
          <span>{{ t('exports.characterCount', { count: content.length.toLocaleString() }) }}</span>
        </section>
      </aside>

      <main class="export-main">
        <section class="preflight-card">
          <header>
            <div>
              <p class="section-kicker">{{ t('exports.preflight') }}</p>
              <h2>{{ t('exports.preflightTitle') }}</h2>
            </div>
            <StatusBadge :tone="exports.blockingIssues.value.length ? 'danger' : 'success'" dot>
              {{
                exports.blockingIssues.value.length
                  ? t('exports.blockingCount', { count: exports.blockingIssues.value.length })
                  : t('exports.ready')
              }}
            </StatusBadge>
          </header>
          <ul class="check-list">
            <li v-for="check in exports.checks.value" :key="check.id" :class="check.level">
              <CheckCircle2 v-if="check.level === 'pass'" :size="17" />
              <AlertTriangle v-else :size="17" />
              <span>{{ check.label }}</span>
            </li>
          </ul>
        </section>

        <section v-if="exports.lastError.value" class="export-error" role="alert">
          <AlertCircle :size="20" />
          <div>
            <strong>{{ exports.lastError.value.summary }}</strong>
            <p>{{ exports.lastError.value.detail }}</p>
          </div>
          <UiButton
            v-if="exports.lastError.value.actionable"
            variant="secondary"
            size="sm"
            @click="askAgentToFix"
          >
            {{ t('exports.askAgentFix') }}
          </UiButton>
        </section>

        <section
          v-if="exports.previewTex.value || exports.previewMessage.value"
          class="preview-card"
        >
          <header>
            <p class="section-kicker">{{ t('exports.preview') }}</p>
            <button type="button" @click="clearPreview">{{ t('general.close') }}</button>
          </header>
          <pre v-if="exports.previewTex.value">{{ exports.previewTex.value }}</pre>
          <p v-else>{{ exports.previewMessage.value }}</p>
        </section>
      </main>

      <aside class="export-history">
        <p class="section-kicker">{{ t('exports.history') }}</p>
        <div v-if="exports.history.value.length" class="history-list">
          <article v-for="record in exports.history.value" :key="record.id">
            <span class="history-format">{{ formatLabel(record.format) }}</span>
            <div>
              <strong>{{ record.title }}</strong>
              <span>{{ new Date(record.created_at).toLocaleString() }}</span>
            </div>
            <StatusBadge :tone="recordTone(record.status)">
              {{ t(`exports.status.${record.status}`) }}
            </StatusBadge>
            <p v-if="record.message">{{ record.message }}</p>
          </article>
        </div>
        <p v-else class="history-empty">{{ t('exports.noHistory') }}</p>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { AlertCircle, AlertTriangle, CheckCircle2, PackageCheck } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import AppHeader from './shell/AppHeader.vue'
import EmptyState from './shell/EmptyState.vue'
import StatusBadge from './shell/StatusBadge.vue'
import UiButton from './ui/UiButton.vue'
import UiSegmented from './ui/UiSegmented.vue'
import {
  useExportWorkspace,
  type ExportFormat,
  type ExportRecordStatus,
} from '../composables/useExportWorkspace'
import { useEditorState } from '../composables/useEditorState'
import { useFileTree } from '../composables/useFileTree'
import { useWorkspaceNavigation } from '../composables/useWorkspaceNavigation'
import { useAgentChat } from '../composables/useAgentChat'
import { useToast } from '../composables/useToast'

const { t } = useI18n()
const exports = useExportWorkspace()
const { activeTab, activeFile, content } = useEditorState()
const { rootDir } = useFileTree()
const workspace = useWorkspaceNavigation()
const agent = useAgentChat()
const { success } = useToast()

const formatOptions = computed(() => [
  { value: 'word' as const, label: 'Word' },
  { value: 'pdf' as const, label: 'PDF' },
  { value: 'latex' as const, label: 'LaTeX' },
])

onMounted(() => void exports.load())
watch(rootDir, () => void exports.load())

async function runExport() {
  if (await exports.runExport()) success(t('exports.exportSuccess'))
}

function clearPreview() {
  exports.previewTex.value = ''
  exports.previewMessage.value = ''
}

function formatLabel(value: ExportFormat) {
  return value === 'word' ? 'DOCX' : value.toUpperCase()
}

function recordTone(status: ExportRecordStatus): 'success' | 'danger' | 'warning' {
  if (status === 'success') return 'success'
  if (status === 'failed') return 'danger'
  return 'warning'
}

async function askAgentToFix() {
  const problem = exports.lastError.value
  if (!problem) return
  workspace.toggleAgentDock(true)
  await agent.sendMessage(
    `请修复当前论文的导出问题，并先展示可审批的差异：${problem.summary}\n\n编译详情：${problem.detail}`,
    content.value,
    '只修改导致导出失败的最小范围；不要静默覆盖未保存内容；文件修改前展示 diff 并等待审批。',
    rootDir.value || undefined,
    activeFile.value || undefined,
    [],
  )
}
</script>

<style scoped>
.export-workspace {
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--c-app-bg);
  color: var(--c-text-0);
}
.export-grid {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-columns: 230px minmax(380px, 1fr) minmax(250px, 310px);
  overflow: hidden;
}
.export-settings,
.export-history {
  min-height: 0;
  overflow: auto;
  padding: 20px;
  background: var(--c-nav);
}
.export-settings {
  border-right: 1px solid var(--c-border);
}
.export-history {
  border-left: 1px solid var(--c-border);
}
.export-settings section {
  display: grid;
  gap: 9px;
  margin-bottom: 24px;
}
.section-kicker,
.export-settings label {
  margin: 0;
  color: var(--c-text-3);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.export-settings select {
  width: 100%;
  height: 36px;
  border: 1px solid var(--c-border);
  border-radius: 7px;
  background: var(--c-panel);
  color: var(--c-text-1);
  padding: 0 9px;
}
.export-settings span {
  color: var(--c-text-3);
  font-size: 11px;
}
.export-settings span.warn {
  color: var(--c-warn);
}
.document-context strong {
  overflow-wrap: anywhere;
  font-size: 14px;
}
.export-main {
  min-height: 0;
  overflow: auto;
  display: grid;
  align-content: start;
  gap: 14px;
  padding: 22px;
}
.preflight-card,
.preview-card,
.export-error {
  border: 1px solid var(--c-border);
  border-radius: 11px;
  background: var(--c-panel);
}
.preflight-card {
  padding: 18px;
}
.preflight-card > header,
.preview-card > header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.preflight-card h2 {
  margin: 4px 0 0;
  font-size: 18px;
}
.check-list {
  display: grid;
  gap: 9px;
  margin: 18px 0 0;
  padding: 0;
  list-style: none;
}
.check-list li {
  display: flex;
  align-items: center;
  gap: 9px;
  color: var(--c-text-1);
  font-size: 13px;
}
.check-list li.pass svg {
  color: var(--c-success);
}
.check-list li.warning svg {
  color: var(--c-warn);
}
.check-list li.error svg {
  color: var(--c-danger);
}
.export-error {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: start;
  gap: 12px;
  padding: 15px;
  border-color: var(--c-danger-border);
  background: var(--c-danger-bg);
  color: var(--c-danger);
}
.export-error strong {
  color: var(--c-danger);
}
.export-error p {
  margin: 5px 0 0;
  color: var(--c-text-2);
  font: 11px/1.5 var(--font-mono);
  white-space: pre-wrap;
}
.preview-card {
  min-height: 180px;
  padding: 16px;
}
.preview-card button {
  border: 0;
  background: transparent;
  color: var(--c-text-3);
  cursor: pointer;
}
.preview-card pre {
  max-height: 460px;
  overflow: auto;
  margin: 14px 0 0;
  padding: 14px;
  border-radius: 8px;
  background: var(--c-surface-2);
  color: var(--c-text-1);
  font: 11px/1.55 var(--font-mono);
  white-space: pre-wrap;
}
.history-list {
  display: grid;
  gap: 9px;
  margin-top: 12px;
}
.history-list article {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  padding: 10px;
  border: 1px solid var(--c-border);
  border-radius: 8px;
  background: var(--c-panel);
}
.history-format {
  color: var(--c-accent);
  font: 700 10px/1 var(--font-mono);
}
.history-list article div {
  min-width: 0;
  display: grid;
  gap: 3px;
}
.history-list strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11px;
}
.history-list article span,
.history-empty {
  color: var(--c-text-3);
  font-size: 9px;
}
.history-list article p {
  grid-column: 1 / -1;
  margin: 0;
  color: var(--c-text-3);
  font-size: 10px;
}
@media (max-width: 1100px) {
  .export-grid {
    grid-template-columns: 210px minmax(360px, 1fr);
  }
  .export-history {
    display: none;
  }
}
@media (max-width: 760px) {
  .export-grid {
    display: block;
    overflow: auto;
  }
  .export-settings {
    border-right: 0;
    border-bottom: 1px solid var(--c-border);
  }
  .export-main {
    overflow: visible;
  }
}
</style>
