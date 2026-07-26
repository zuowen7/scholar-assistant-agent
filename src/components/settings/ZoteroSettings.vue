<template>
  <div class="zotero-settings">
    <div class="zotero-guide">
      <div>
        <strong>{{ t('settings.zoteroApi') }}</strong>
        <p>{{ t('settings.zoteroSetupGuide') }}</p>
      </div>
      <a href="https://www.zotero.org/settings/keys" target="_blank" rel="noopener noreferrer">
        {{ t('settings.zoteroOpenKeys') }}
      </a>
    </div>

    <div class="form-section">
      <label class="field">
        <span>{{ t('settings.apiKey') }}</span>
        <input
          v-model="apiKey"
          data-test="zotero-api-key"
          type="password"
          autocomplete="off"
          :placeholder="
            hasStoredKey ? t('settings.zoteroKeyStored') : t('settings.zoteroKeyPlaceholder')
          "
        />
      </label>
      <label class="field">
        <span>{{ t('settings.zoteroUserId') }}</span>
        <input
          v-model="userId"
          data-test="zotero-user-id"
          inputmode="numeric"
          autocomplete="off"
          :placeholder="t('settings.zoteroUserIdPlaceholder')"
        />
      </label>
      <label class="field">
        <span>{{ t('settings.zoteroStyle') }}</span>
        <select v-model="style" data-test="zotero-style">
          <option value="ieee">IEEE</option>
          <option value="apa">APA 7</option>
          <option value="chicago-author-date">Chicago Author-Date</option>
          <option value="nature">Nature</option>
        </select>
      </label>
    </div>

    <p class="form-hint">{{ t('settings.zoteroHint') }}</p>
    <div class="action-row">
      <UiButton
        data-test="zotero-check"
        variant="secondary"
        size="sm"
        :loading="checking"
        @click="checkConnection"
      >
        {{ t('settings.zoteroCheck') }}
      </UiButton>
      <UiButton
        data-test="zotero-save"
        variant="primary"
        size="sm"
        :loading="saving"
        :disabled="!canSave"
        @click="saveConfig"
      >
        {{ t('settings.zoteroSave') }}
      </UiButton>
    </div>

    <p
      v-if="statusMessage"
      data-test="zotero-status"
      class="zotero-status"
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

const apiKey = ref('')
const userId = ref('')
const style = ref('ieee')
const hasStoredKey = ref(false)
const saving = ref(false)
const checking = ref(false)
const statusKind = ref<'ok' | 'error'>('ok')
const statusMessage = ref('')

const canSave = computed(
  () => Boolean(userId.value.trim()) && (hasStoredKey.value || Boolean(apiKey.value.trim())),
)

async function loadConfig() {
  try {
    const response = await fetch(`${API_BASE}/api/config`)
    if (!response.ok) throw new Error(t('settings.zoteroBackendError'))
    const config = await response.json()
    const zotero = config.zotero || {}
    hasStoredKey.value = typeof zotero.api_key === 'string' && zotero.api_key.includes('****')
    apiKey.value = hasStoredKey.value ? '' : zotero.api_key || ''
    userId.value = String(zotero.user_id || '')
    style.value = String(zotero.style || 'ieee')
  } catch {
    showStatus('error', t('settings.zoteroNetworkError'))
  }
}

async function saveConfig() {
  if (!canSave.value) return
  saving.value = true
  statusMessage.value = ''
  try {
    const zotero: Record<string, string> = {
      user_id: userId.value.trim(),
      style: style.value,
    }
    const nextApiKey = apiKey.value.trim()
    if (nextApiKey) zotero.api_key = nextApiKey
    const response = await fetch(`${API_BASE}/api/config`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ zotero }),
    })
    if (!response.ok) throw new Error(t('settings.zoteroSaveFailed'))
    if (nextApiKey) {
      hasStoredKey.value = true
      apiKey.value = ''
    }
    showStatus('ok', t('settings.zoteroSaved'))
  } catch (error) {
    showStatus('error', error instanceof Error ? error.message : t('settings.zoteroSaveFailed'))
  } finally {
    saving.value = false
  }
}

async function checkConnection() {
  checking.value = true
  statusMessage.value = ''
  try {
    const response = await fetch(`${API_BASE}/api/zotero/status?verify=true`)
    if (!response.ok) throw new Error(t('settings.zoteroBackendError'))
    const result = await response.json()
    showStatus(
      result.connected && result.verified ? 'ok' : 'error',
      result.connected && result.verified
        ? t('settings.zoteroConfigured')
        : result.message || t('settings.zoteroNotConfigured'),
    )
  } catch (error) {
    showStatus('error', error instanceof Error ? error.message : t('settings.zoteroNetworkError'))
  } finally {
    checking.value = false
  }
}

function showStatus(kind: 'ok' | 'error', message: string) {
  statusKind.value = kind
  statusMessage.value = message
}

onMounted(loadConfig)
</script>

<style scoped>
.zotero-settings {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.zotero-guide {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-5);
  padding: var(--space-5);
  border: 1px solid var(--c-surface-3);
  border-radius: var(--radius-md);
  background: var(--c-surface-1);
}

.zotero-guide strong {
  color: var(--c-text-0);
  font-size: var(--text-md);
}

.zotero-guide p {
  margin: 5px 0 0;
  color: var(--c-text-3);
  font-size: var(--text-sm);
  line-height: 1.55;
}

.zotero-guide a {
  flex: 0 0 auto;
  color: var(--c-accent);
  font-size: var(--text-sm);
  font-weight: 600;
  text-decoration: none;
}

.zotero-guide a:hover {
  text-decoration: underline;
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

.field input,
.field select {
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

.field input:focus,
.field select:focus {
  border-color: var(--c-accent);
  box-shadow: var(--ring-focus);
}

.form-hint {
  margin: 0;
  color: var(--c-text-3);
  font-size: var(--text-sm);
}

.action-row {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-3);
}

.zotero-status {
  margin: 0;
  padding: 9px 11px;
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
}

.zotero-status.ok {
  color: var(--c-success);
  background: color-mix(in srgb, var(--c-success) 10%, transparent);
}

.zotero-status.error {
  color: var(--c-danger);
  background: var(--c-danger-bg);
}

@media (max-width: 720px) {
  .zotero-guide {
    flex-direction: column;
  }

  .form-section {
    grid-template-columns: 1fr;
  }
}
</style>
