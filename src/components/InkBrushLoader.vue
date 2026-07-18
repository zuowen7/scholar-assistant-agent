<template>
  <div
    class="loader"
    :class="[`loader--${size}`, { 'loader--overlay': overlay }]"
    role="status"
    aria-live="polite"
    :aria-label="text"
  >
    <div class="loader__panel">
      <div class="loader__mark" aria-hidden="true">研</div>
      <div class="loader__copy">
        <strong v-if="overlay">研墨</strong>
        <span v-if="text">{{ text }}</span>
      </div>
      <span class="loader__progress" aria-hidden="true"><i /></span>
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  text?: string
  size?: 'small' | 'medium' | 'large'
  overlay?: boolean
}>(), {
  text: '',
  size: 'medium',
  overlay: false,
})
</script>

<style scoped>
.loader {
  --loader-size: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--c-text-0);
}

.loader--small { --loader-size: 32px; }
.loader--large { --loader-size: 48px; }

.loader--overlay {
  position: fixed;
  inset: 0;
  z-index: 1200;
  width: 100vw;
  height: 100vh;
  background: var(--c-app-bg);
}

.loader__panel {
  display: grid;
  min-width: 210px;
  grid-template-columns: var(--loader-size) minmax(0, 1fr);
  align-items: center;
  gap: 12px;
  padding: 16px 18px;
  border: 1px solid var(--c-border);
  border-radius: 10px;
  background: var(--c-panel-bg);
}

.loader--overlay .loader__panel { min-width: 248px; }

.loader__mark {
  display: grid;
  width: var(--loader-size);
  height: var(--loader-size);
  place-items: center;
  border-radius: 9px;
  background: var(--c-brand, #c8503a);
  color: #fffaf4;
  font-family: var(--font-serif-zh);
  font-size: calc(var(--loader-size) * .52);
  font-weight: 700;
}

.loader__copy {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 3px;
}

.loader__copy strong { font-family: var(--font-serif-zh); font-size: 18px; letter-spacing: .08em; }
.loader__copy span { color: var(--c-text-2); font-size: 12px; line-height: 1.45; }

.loader__progress {
  position: relative;
  grid-column: 1 / -1;
  height: 2px;
  overflow: hidden;
  border-radius: 2px;
  background: var(--c-surface-3);
}

.loader__progress i {
  position: absolute;
  inset: 0 auto 0 0;
  width: 42%;
  border-radius: inherit;
  background: var(--c-accent);
  animation: loader-travel 1.35s var(--ease-out) infinite;
}

@keyframes loader-travel {
  from { transform: translateX(-110%); }
  to { transform: translateX(345%); }
}

@media (prefers-reduced-motion: reduce) {
  .loader__progress i { width: 60%; animation: none; }
}
</style>
