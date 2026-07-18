<template>
  <Teleport to="body">
    <Transition name="app-dialog">
      <div
        v-if="modelValue"
        class="app-dialog-layer"
        :class="`app-dialog-layer--${variant}`"
        @mousedown.self="onBackdrop"
      >
        <section
          ref="dialog"
          class="app-dialog"
          :class="`app-dialog--${variant}`"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="titleId"
          :aria-describedby="subtitle ? subtitleId : undefined"
          tabindex="-1"
          @keydown="onKeydown"
        >
          <header class="app-dialog__header">
            <div class="app-dialog__heading">
              <h2 :id="titleId">{{ title }}</h2>
              <p v-if="subtitle" :id="subtitleId">{{ subtitle }}</p>
            </div>
            <button class="app-dialog__close" type="button" :aria-label="closeLabel" @click="close">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="m7 7 10 10M17 7 7 17" />
              </svg>
            </button>
          </header>
          <div class="app-dialog__body">
            <slot />
          </div>
          <footer v-if="$slots.footer" class="app-dialog__footer">
            <slot name="footer" />
          </footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'

const props = withDefaults(defineProps<{
  modelValue: boolean
  title: string
  subtitle?: string
  closeLabel?: string
  variant?: 'dialog' | 'drawer'
  closeOnBackdrop?: boolean
}>(), {
  subtitle: '',
  closeLabel: 'Close',
  variant: 'dialog',
  closeOnBackdrop: true,
})

const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
const dialog = ref<HTMLElement | null>(null)
let previousFocus: HTMLElement | null = null

const titleId = `app-dialog-title-${Math.random().toString(36).slice(2)}`
const subtitleId = `${titleId}-subtitle`

function close() {
  emit('update:modelValue', false)
}

function onBackdrop() {
  if (props.closeOnBackdrop) close()
}

function focusableElements() {
  return Array.from(dialog.value?.querySelectorAll<HTMLElement>(
    'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
  ) ?? []).filter(element => !element.hasAttribute('hidden'))
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    close()
    return
  }
  if (event.key !== 'Tab') return
  const focusable = focusableElements()
  if (!focusable.length) {
    event.preventDefault()
    dialog.value?.focus()
    return
  }
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

watch(() => props.modelValue, async (open) => {
  if (open) {
    previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    document.body.classList.add('app-dialog-open')
    await nextTick()
    focusableElements()[0]?.focus() ?? dialog.value?.focus()
  } else {
    document.body.classList.remove('app-dialog-open')
    previousFocus?.focus()
    previousFocus = null
  }
})

onBeforeUnmount(() => document.body.classList.remove('app-dialog-open'))
</script>

<style scoped>
.app-dialog-layer {
  position: fixed;
  inset: 0;
  z-index: 3000;
  display: grid;
  place-items: center;
  padding: 28px;
  background: color-mix(in srgb, var(--c-text-0) 26%, transparent);
  backdrop-filter: blur(3px);
}

.app-dialog-layer--drawer {
  place-items: stretch end;
  padding: 0;
}

.app-dialog {
  display: flex;
  width: min(680px, calc(100vw - 48px));
  max-height: min(760px, calc(100vh - 56px));
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--c-border);
  border-radius: 12px;
  background: var(--c-panel);
  box-shadow: var(--elevation-4);
  color: var(--c-text-0);
  outline: none;
}

.app-dialog--drawer {
  width: min(760px, calc(100vw - 72px));
  height: 100vh;
  max-height: 100vh;
  border-width: 0 0 0 1px;
  border-radius: 0;
}

.app-dialog__header {
  display: flex;
  min-height: 76px;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  padding: 20px 22px 16px;
  border-bottom: 1px solid var(--c-border);
}

.app-dialog__heading h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 650;
  letter-spacing: -.015em;
}

.app-dialog__heading p {
  margin: 5px 0 0;
  color: var(--c-text-2);
  font-size: 12px;
  line-height: 1.5;
}

.app-dialog__close {
  display: grid;
  width: 32px;
  height: 32px;
  flex: 0 0 auto;
  place-items: center;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--c-text-2);
  cursor: pointer;
}

.app-dialog__close:hover { background: var(--c-surface-2); color: var(--c-text-0); }
.app-dialog__close:focus-visible { outline: none; box-shadow: var(--ring-focus); }
.app-dialog__close svg { width: 18px; fill: none; stroke: currentColor; stroke-width: 1.7; }

.app-dialog__body {
  min-height: 0;
  flex: 1;
  overflow: auto;
  overscroll-behavior: contain;
}

.app-dialog__footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 14px 22px;
  border-top: 1px solid var(--c-border);
}

.app-dialog-enter-active,
.app-dialog-leave-active { transition: opacity var(--motion-base) var(--ease-out); }
.app-dialog-enter-active .app-dialog,
.app-dialog-leave-active .app-dialog { transition: transform var(--motion-base) var(--ease-out), opacity var(--motion-base); }
.app-dialog-enter-from,
.app-dialog-leave-to { opacity: 0; }
.app-dialog-enter-from .app-dialog,
.app-dialog-leave-to .app-dialog { opacity: 0; transform: translateY(8px) scale(.99); }
.app-dialog-layer--drawer.app-dialog-enter-from .app-dialog,
.app-dialog-layer--drawer.app-dialog-leave-to .app-dialog { transform: translateX(24px); }

@media (max-width: 720px) {
  .app-dialog-layer { padding: 0; place-items: end stretch; }
  .app-dialog,
  .app-dialog--drawer {
    width: 100%;
    height: min(92vh, 820px);
    max-height: 92vh;
    border-width: 1px 0 0;
    border-radius: 12px 12px 0 0;
  }
}
</style>

<style>
body.app-dialog-open { overflow: hidden; }
</style>
