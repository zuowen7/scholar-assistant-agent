<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { Mic } from 'lucide-vue-next'
import { useVoiceCommand } from '../composables/useVoiceCommand'

const { t } = useI18n()
const { state, transcript, response, error, cancel } = useVoiceCommand()

const statusText = computed(() => {
  if (error.value) return ''
  const name = wakeWordName.value
  switch (state.value) {
    case 'listening': return `${name}${t('voice.listening')}`
    case 'submitting': return t('voice.processing')
    case 'processing': return t('voice.processing')
    default: return ''
  }
})

const wakeWordName = computed(() => {
  try {
    const raw = localStorage.getItem('voice-settings')
    if (raw) {
      const s = JSON.parse(raw)
      if (s.wakeWordPhrase) return s.wakeWordPhrase
    }
  } catch { /* ignore */ }
  return '小研'
})

const showRipples = computed(() => state.value === 'listening')

function onBackdropClick() { cancel() }
function onKeydown(e: KeyboardEvent) { if (e.key === 'Escape') cancel() }

onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
    <Transition name="va-fade">
      <div v-if="state !== 'idle'" class="va-overlay" @keydown="onKeydown">
        <div class="va-backdrop" @click="onBackdropClick" />

        <div class="va-content">
          <!-- Orb with ripple animations -->
          <div class="va-orb-wrapper">
            <!-- Ripple rings (listening only) -->
            <div v-if="showRipples" class="va-ripple va-ripple-1" />
            <div v-if="showRipples" class="va-ripple va-ripple-2" />
            <div v-if="showRipples" class="va-ripple va-ripple-3" />

            <!-- Central orb -->
            <div class="va-orb" :class="{ 'va-orb--active': state === 'listening' }">
              <Mic class="va-orb-icon" />
            </div>
          </div>

          <!-- Status text -->
          <div class="va-status">{{ statusText }}</div>

          <!-- Live transcript -->
          <Transition name="va-text">
            <div v-if="transcript" class="va-transcript">{{ transcript }}</div>
          </Transition>

          <!-- Agent response -->
          <Transition name="va-text">
            <div v-if="response" class="va-response">{{ response }}</div>
          </Transition>

          <!-- Error -->
          <Transition name="va-text">
            <div v-if="error" class="va-error">{{ error }}</div>
          </Transition>
        </div>
      </div>
    </Transition>
</template>

<style scoped>
/* ── Overlay ─────────────────────────────────────────────────────────── */
.va-overlay {
  position: fixed;
  inset: 0;
  z-index: 900;
  display: flex;
  align-items: center;
  justify-content: center;
}

.va-backdrop {
  position: absolute;
  inset: 0;
  background: var(--va-backdrop-bg);
  backdrop-filter: blur(40px);
  -webkit-backdrop-filter: blur(40px);
  cursor: pointer;
}

/* Dark theme: dark translucent backdrop */
:root[data-theme="dark"] .va-backdrop { --va-backdrop-bg: rgba(0, 0, 0, 0.6); }
/* Light theme: light translucent backdrop */
:root[data-theme="light"] .va-backdrop { --va-backdrop-bg: rgba(255, 255, 255, 0.7); }

.va-content {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
  max-width: 560px;
  width: 90%;
}

/* ── Orb ─────────────────────────────────────────────────────────────── */
.va-orb-wrapper {
  position: relative;
  width: 160px;
  height: 160px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.va-orb {
  width: 120px;
  height: 120px;
  border-radius: 50%;
  background: radial-gradient(circle at 40% 40%, var(--c-accent-soft), var(--c-accent));
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.3s ease, box-shadow 0.3s ease;
}

.va-orb--active {
  animation: va-breathe 2s ease-in-out infinite;
}

/* Dark theme: white icon; Light theme: white icon still (accent bg is dark enough) */
.va-orb-icon {
  width: 40px;
  height: 40px;
  color: #fff;
  opacity: 0.95;
}

/* ── Ripple ──────────────────────────────────────────────────────────── */
.va-ripple {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 2px solid var(--c-accent);
  opacity: 0;
  animation: va-ripple-out 2.5s ease-out infinite;
}

.va-ripple-1 { animation-delay: 0s; }
.va-ripple-2 { animation-delay: 0.6s; }
.va-ripple-3 { animation-delay: 1.2s; }

/* ── Text elements ───────────────────────────────────────────────────── */
.va-status {
  font-size: 18px;
  font-weight: 500;
  color: var(--c-text-1);
  text-align: center;
}

.va-transcript {
  font-size: 24px;
  font-weight: 600;
  color: var(--c-text-0);
  text-align: center;
  line-height: 1.5;
  max-width: 100%;
  word-break: break-word;
}

.va-response {
  font-size: 16px;
  color: var(--c-text-2);
  text-align: center;
  line-height: 1.6;
  max-height: 200px;
  overflow-y: auto;
  max-width: 100%;
  word-break: break-word;
}

.va-error {
  font-size: 14px;
  color: var(--c-warn);
  text-align: center;
}

/* ── Animations ──────────────────────────────────────────────────────── */
@keyframes va-breathe {
  0%, 100% {
    transform: scale(1);
    box-shadow: 0 0 0 0 rgba(91, 108, 255, 0.4);
  }
  50% {
    transform: scale(1.08);
    box-shadow: 0 0 60px 20px rgba(91, 108, 255, 0.15);
  }
}

/* Light theme: softer glow */
:root[data-theme="light"] .va-orb--active {
  animation: va-breathe-light 2s ease-in-out infinite;
}
@keyframes va-breathe-light {
  0%, 100% {
    transform: scale(1);
    box-shadow: 0 0 0 0 rgba(91, 108, 255, 0.25);
  }
  50% {
    transform: scale(1.08);
    box-shadow: 0 0 40px 15px rgba(91, 108, 255, 0.10);
  }
}

@keyframes va-ripple-out {
  0% {
    transform: scale(0.75);
    opacity: 0.6;
  }
  100% {
    transform: scale(2.2);
    opacity: 0;
  }
}

/* ── Transitions ─────────────────────────────────────────────────────── */
.va-fade-enter-active { transition: opacity 200ms ease-out; }
.va-fade-leave-active { transition: opacity 150ms ease-in; }
.va-fade-enter-from,
.va-fade-leave-to { opacity: 0; }

.va-text-enter-active { transition: opacity 200ms ease-out, transform 200ms ease-out; }
.va-text-leave-active { transition: opacity 100ms ease-in; }
.va-text-enter-from { opacity: 0; transform: translateY(8px); }
.va-text-leave-to { opacity: 0; }
</style>
