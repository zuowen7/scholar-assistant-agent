<template>
  <div class="vision-settings">
    <div class="vision-guide">
      <div>
        <strong>{{ t('settings.visionApi') }}</strong>
        <p>{{ t('settings.visionSetupGuide') }}</p>
      </div>
    </div>

    <div class="form-section">
      <label class="field field-wide">
        <span>{{ t('settings.visionBaseUrl') }}</span>
        <input
          v-model="baseUrl"
          data-test="vision-base-url"
          type="url"
          autocomplete="off"
          placeholder="https://api.openai.com/v1"
        />
      </label>
      <label class="field">
        <span>{{ t('settings.visionModel') }}</span>
        <input
          v-model="model"
          data-test="vision-model"
          autocomplete="off"
          placeholder="gpt-4o / glm-4v-flash"
        />
      </label>
      <label class="field">
        <span>{{ t('settings.apiKey') }}</span>
        <input
          v-model="apiKey"
          data-test="vision-api-key"
          type="password"
          autocomplete="off"
          :placeholder="
            hasStoredKey ? t('settings.visionKeyStored') : t('settings.visionKeyPlaceholder')
          "
        />
      </label>
    </div>

    <div class="action-row">
      <UiButton
        data-test="vision-save"
        variant="primary"
        size="sm"
        :loading="saving"
        :disabled="!canSave"
        @click="saveConfig"
      >
        {{ t('settings.visionSave') }}
      </UiButton>
    </div>

    <p
      v-if="statusMessage"
      data-test="vision-status"
      class="vision-status"
      :class="statusKind"
      role="status"
    >
      {{ statusKind === 'ok' ? '✓' : '!' }} {{ statusMessage }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { API_BASE } from '../../utils/api'
import UiButton from '../ui/UiButton.vue'

const { t } = useI18n()

const baseUrl = ref('')
const model = ref('')
const apiKey = ref('')
const hasStoredKey = ref(false)
const saving = ref(false)
const statusKind = ref<'ok' | 'error'>('ok')
const statusMessage = ref('')

const canSave = computed(() => Boolean(baseUrl.value.trim()) && Boolean(model.value.trim()))

async function loadConfig() {
  try {
    const response = await fetch(`${API_BASE}/api/config`)
    if (!response.ok) throw new Error(t('settings.zoteroBackendError'))
    const config = await response.json()
    const vision = config.vision || {}
    hasStoredKey.value = typeof vision.api_key === 'string' && vision.api_key.includes('****')
    apiKey.value = hasStoredKey.value ? '' : vision.api_key || ''
    baseUrl.value = vision.base_url || 'https://api.openai.com/v1'
    model.value = vision.model || ''
  } catch {
    showStatus('error', t('settings.zoteroNetworkError'))
  }
}

async function saveConfig() {
  if (!canSave.value) return
  saving.value = true
  statusMessage.value = ''
  try {
    const vision: Record<string, string> = {
      base_url: baseUrl.value.trim(),
      model: model.value.trim(),
    }
    const nextApiKey = apiKey.value.trim()
    if (nextApiKey) vision.api_key = nextApiKey
    const response = await fetch(`${API_BASE}/api/config`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ vision }),
    })
    if (!response.ok) throw new Error(t('settings.visionSaveFailed'))
    if (nextApiKey) {
      hasStoredKey.value = true
      apiKey.value = ''
    }
    showStatus('ok', t('settings.visionSaved'))
  } catch (error) {
    showStatus('error', error instanceof Error ? error.message : t('settings.visionSaveFailed'))
  } finally {
    saving.value = false
  }
}

function showStatus(kind: 'ok' | 'error', message: string) {
  statusKind.value = kind
  statusMessage.value = message
}

onMounted(loadConfig)
</script>

<style scoped>
.vision-settings {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.vision-guide {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-5);
  padding: var(--space-5);
  border: 1px solid var(--c-surface-3);
  border-radius: var(--radius-md);
  background: var(--c-surface-1);
}

.vision-guide strong {
  color: var(--c-text-0);
  font-size: var(--text-md);
}

.vision-guide p {
  margin: 5px 0 0;
  color: var(--c-text-3);
  font-size: var(--text-sm);
  line-height: 1.55;
}

.form-section {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-4);
}

.field {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 7px;
  color: var(--c-text-2);
  font-size: var(--text-sm);
}

.field-wide {
  grid-column: 1 / -1;
}

.field input {
  width: 100%;
  min-width: 0;
  height: 36px;
  box-sizing: border-box;
  padding: 0 10px;
  border: 1px solid var(--c-surface-4);
  border-radius: var(--radius-sm);
  outline: none;
  background: var(--c-surface-1);
  color: var(--c-text-1);
  font: inherit;
}

.field input:focus {
  border-color: var(--c-accent);
  box-shadow: var(--ring-focus);
}

.action-row {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-3);
}

.vision-status {
  margin: 0;
  padding: 9px 11px;
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
}

.vision-status.ok {
  color: var(--c-success);
  background: color-mix(in srgb, var(--c-success) 10%, transparent);
}

.vision-status.error {
  color: var(--c-danger);
  background: var(--c-danger-bg);
}

@media (max-width: 720px) {
  .form-section {
    grid-template-columns: 1fr;
  }

  .field-wide {
    grid-column: auto;
  }
}
</style>
