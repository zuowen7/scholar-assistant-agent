<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { Mic, X } from 'lucide-vue-next'
import { useVoiceCommand } from '../composables/useVoiceCommand'
import { useVoiceRouter } from '../composables/useVoiceRouter'

const { t } = useI18n()
const { state, transcript, response, error, cancel, triggerVoiceCommand } = useVoiceCommand()
const router = useVoiceRouter()

const wakeWordName = computed(() => {
  try {
    const raw = localStorage.getItem('voice-settings')
    if (raw) {
      const settings = JSON.parse(raw)
      if (settings.wakeWordPhrase) return settings.wakeWordPhrase
    }
  } catch {
    /* localStorage can be unavailable */
  }
  return '小研'
})

const statusText = computed(() => {
  if (error.value) return t('voice.error')
  if (state.value === 'result') return t('voice.done')
  if (state.value === 'listening') return `${wakeWordName.value}${t('voice.listening')}`
  if (state.value === 'submitting' || state.value === 'processing') return t('voice.processing')
  return ''
})
const showRipples = computed(() => state.value === 'listening')
const commandFeedback = computed(() => {
  if (state.value !== 'result' && state.value !== 'error') return null
  const result = router.lastCommandResult.value
  if (!result || result.type === 'chat') return null
  const locale = localStorage.getItem('locale') || 'zh-CN'
  const label = locale === 'zh-CN' ? result.label?.zh : result.label?.en
  return { text: label || result.commandId || '', success: result.success, error: result.error }
})

function onBackdropClick() {
  cancel()
}
function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') cancel()
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <Transition name="va-fade">
    <div v-if="state !== 'idle'" class="va-overlay">
      <div class="va-backdrop" @click="onBackdropClick" />
      <section class="va-content" role="dialog" aria-modal="true" :aria-label="t('voice.title')">
        <header class="va-header">
          <div class="va-title-row">
            <div class="va-orb-wrapper" aria-hidden="true">
              <span v-if="showRipples" class="va-ripple va-ripple-1" />
              <span v-if="showRipples" class="va-ripple va-ripple-2" />
              <span v-if="showRipples" class="va-ripple va-ripple-3" />
              <span class="va-orb" :class="{ 'va-orb--active': state === 'listening' }"
                ><Mic class="va-orb-icon"
              /></span>
            </div>
            <div>
              <p>{{ t('voice.title') }}</p>
              <strong class="va-status">{{ statusText }}</strong>
            </div>
          </div>
          <button type="button" :aria-label="t('general.close')" @click="cancel">
            <X :size="17" />
          </button>
        </header>

        <div class="va-body">
          <div v-if="transcript" class="va-transcript" :data-label="t('voice.transcript')">
            <p>{{ transcript }}</p>
          </div>
          <div v-else-if="state === 'listening'" class="va-listening-note">
            {{ t('voice.speakNow') }}
          </div>

          <Transition name="va-text">
            <div v-if="response" class="va-response">
              <span>{{ t('voice.result') }}</span>
              <p>{{ response }}</p>
            </div>
          </Transition>

          <Transition name="va-text">
            <div
              v-if="commandFeedback"
              class="va-cmd-feedback"
              :class="commandFeedback.success ? 'va-cmd-ok' : 'va-cmd-err'"
            >
              <span class="va-cmd-icon">{{ commandFeedback.success ? '✓' : '!' }}</span>
              <div>
                <strong>{{ commandFeedback.text }}</strong>
                <p v-if="commandFeedback.error" class="va-cmd-error-detail">
                  {{ commandFeedback.error }}
                </p>
              </div>
            </div>
          </Transition>

          <Transition name="va-text"
            ><div v-if="error" class="va-error" role="alert">{{ error }}</div></Transition
          >
          <div v-if="state === 'error'" class="va-error-actions">
            <button type="button" class="va-retry" @click="triggerVoiceCommand">
              {{ t('voice.retry') }}
            </button>
            <button type="button" class="va-dismiss" @click="cancel">
              {{ t('general.close') }}
            </button>
          </div>
        </div>

        <footer><span>Esc</span>{{ t('voice.cancelHint') }}</footer>
      </section>
    </div>
  </Transition>
</template>

<style scoped>
.va-overlay {
  position: fixed;
  inset: 0;
  z-index: 2900;
  display: grid;
  place-items: center;
  padding: 24px;
}
.va-backdrop {
  position: absolute;
  inset: 0;
  background: color-mix(in srgb, var(--c-text-0) 24%, transparent);
  backdrop-filter: blur(4px);
  cursor: pointer;
}
.va-content {
  position: relative;
  z-index: 1;
  display: flex;
  width: min(500px, calc(100vw - 40px));
  max-height: min(650px, calc(100vh - 48px));
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--c-border);
  border-radius: 12px;
  background: var(--c-panel);
  box-shadow: var(--elevation-4);
  color: var(--c-text-0);
}
.va-header {
  display: flex;
  min-height: 76px;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 15px 18px;
  border-bottom: 1px solid var(--c-border);
}
.va-title-row {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 13px;
}
.va-title-row > div:last-child {
  min-width: 0;
}
.va-title-row p {
  margin: 0 0 3px;
  color: var(--c-text-3);
  font-size: 11px;
}
.va-status {
  display: block;
  overflow: hidden;
  color: var(--c-text-0);
  font-family: var(--font-serif-zh);
  font-size: 16px;
  font-weight: 630;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.va-header button {
  display: grid;
  width: 30px;
  height: 30px;
  flex: 0 0 auto;
  place-items: center;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--c-text-2);
  cursor: pointer;
}
.va-header button:hover {
  background: var(--c-surface-2);
  color: var(--c-text-0);
}
.va-header button:focus-visible {
  outline: none;
  box-shadow: var(--ring-focus);
}
.va-orb-wrapper {
  position: relative;
  display: grid;
  width: 46px;
  height: 46px;
  flex: 0 0 auto;
  place-items: center;
}
.va-orb {
  display: grid;
  width: 40px;
  height: 40px;
  place-items: center;
  border: 1px solid var(--c-border);
  border-radius: 10px;
  background: var(--c-accent-soft);
  color: var(--c-accent);
}
.va-orb-icon {
  width: 19px;
  height: 19px;
}
.va-orb--active {
  border-color: color-mix(in srgb, var(--c-accent) 45%, var(--c-border));
}
.va-ripple {
  position: absolute;
  bottom: -1px;
  left: 50%;
  z-index: 2;
  width: 2px;
  height: 7px;
  border-radius: 2px;
  background: var(--c-accent);
  animation: va-level 900ms ease-in-out infinite alternate;
}
.va-ripple-1 {
  margin-left: -7px;
  animation-delay: -500ms;
}
.va-ripple-2 {
  height: 10px;
  margin-left: -1px;
  animation-delay: -250ms;
}
.va-ripple-3 {
  margin-left: 5px;
}
.va-body {
  min-height: 160px;
  overflow-y: auto;
  padding: 20px 22px 24px;
}
.va-transcript,
.va-response {
  padding: 13px 0;
}
.va-transcript + .va-response {
  border-top: 1px solid var(--c-border);
}
.va-transcript::before,
.va-response > span {
  display: block;
  margin-bottom: 7px;
  color: var(--c-text-3);
  font-size: 10px;
  font-weight: 620;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.va-transcript::before {
  content: attr(data-label);
}
.va-transcript p,
.va-response p {
  margin: 0;
  overflow-wrap: anywhere;
  line-height: 1.7;
}
.va-transcript p {
  font-family: var(--font-serif-zh);
  font-size: 19px;
}
.va-response p {
  color: var(--c-text-1);
  font-size: 13px;
}
.va-listening-note {
  display: grid;
  min-height: 120px;
  place-items: center;
  color: var(--c-text-3);
  font-size: 13px;
}
.va-cmd-feedback {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-top: 12px;
  padding: 11px 12px;
  border-left: 3px solid var(--c-success);
  background: var(--c-success-bg);
  color: var(--c-success-fg);
  font-size: 12px;
}
.va-cmd-err {
  border-left-color: var(--c-warn);
  background: var(--c-warn-bg);
  color: var(--c-warn-fg);
}
.va-cmd-icon {
  display: grid;
  width: 18px;
  height: 18px;
  place-items: center;
  border: 1px solid currentColor;
  border-radius: 50%;
  font-size: 11px;
}
.va-cmd-feedback strong {
  font-weight: 620;
}
.va-cmd-error-detail {
  margin: 4px 0 0;
  opacity: 0.8;
  font-size: 11px;
  line-height: 1.5;
}
.va-error {
  margin-top: 12px;
  padding: 11px 12px;
  border-left: 3px solid var(--c-danger);
  background: var(--c-danger-bg);
  color: var(--c-danger-fg);
  font-size: 12px;
  line-height: 1.55;
  overflow-wrap: anywhere;
}
.va-error-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 14px;
}
.va-error-actions button {
  min-height: 32px;
  padding: 0 13px;
  border: 1px solid var(--c-border);
  border-radius: 8px;
  background: var(--c-panel);
  color: var(--c-text-1);
  font: inherit;
  cursor: pointer;
}
.va-error-actions button:hover {
  border-color: var(--c-border-strong);
  color: var(--c-text-0);
}
.va-error-actions button:focus-visible {
  outline: none;
  box-shadow: var(--ring-focus);
}
.va-error-actions .va-retry {
  border-color: var(--c-accent);
  background: var(--c-accent);
  color: var(--c-on-accent);
}
footer {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding: 10px 18px;
  border-top: 1px solid var(--c-border);
  color: var(--c-text-3);
  font-size: 10px;
}
footer span {
  padding: 2px 6px;
  border: 1px solid var(--c-border);
  border-radius: 4px;
  background: var(--c-surface-1);
  color: var(--c-text-2);
  font-family: var(--font-mono);
}
@keyframes va-level {
  from {
    transform: scaleY(0.45);
    opacity: 0.45;
  }
  to {
    transform: scaleY(1);
    opacity: 1;
  }
}
.va-fade-enter-active,
.va-fade-leave-active {
  transition: opacity var(--motion-fast) var(--ease-out);
}
.va-fade-enter-from,
.va-fade-leave-to {
  opacity: 0;
}
.va-text-enter-active,
.va-text-leave-active {
  transition:
    opacity var(--motion-fast) var(--ease-out),
    transform var(--motion-fast) var(--ease-out);
}
.va-text-enter-from {
  opacity: 0;
  transform: translateY(4px);
}
.va-text-leave-to {
  opacity: 0;
}
@media (prefers-reduced-motion: reduce) {
  .va-ripple {
    animation: none;
  }
}
</style>
