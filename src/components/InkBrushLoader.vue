<template>
  <div
    class="ink-brush-loader"
    :class="[`ink-brush-loader--${size}`, { 'ink-brush-loader--overlay': overlay }]"
    role="status"
    aria-live="polite"
    :aria-label="text"
  >
    <!-- Splash image background -->
    <div v-if="overlay" class="splash-stage">
      <img
        :src="splashUrl"
        alt=""
        class="splash-image"
        :class="{ 'splash-image--loaded': imageReady }"
        @load="onImageLoad"
      />
      <div class="splash-overlay" />

      <!-- Serif brand title -->
      <div class="splash-brand" :class="{ 'splash-brand--visible': brandVisible }">
        <div class="splash-pillar" />
        <h1 class="splash-title">研墨</h1>
      </div>
      <p class="splash-subtitle" :class="{ 'splash-subtitle--visible': subtitleVisible }">
        Scholar Translator
      </p>
    </div>

    <!-- Non-overlay mode: compact loader -->
    <div v-else class="ink-brush-loader__panel">
      <div class="ink-brush-loader__stage" aria-hidden="true">
        <svg class="ink-brush-loader__ring" viewBox="0 0 160 160">
          <defs>
            <linearGradient id="inkTone" x1="34" y1="22" x2="132" y2="132" gradientUnits="userSpaceOnUse">
              <stop offset="0" stop-color="currentColor" stop-opacity="0.42" />
              <stop offset="0.38" stop-color="currentColor" stop-opacity="0.88" />
              <stop offset="0.72" stop-color="currentColor" stop-opacity="0.64" />
              <stop offset="1" stop-color="currentColor" stop-opacity="0.34" />
            </linearGradient>
            <filter id="inkBloom" x="-18%" y="-18%" width="136%" height="136%">
              <feGaussianBlur stdDeviation="1.7" result="blur" />
              <feColorMatrix in="blur" type="matrix" values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 .48 0" />
            </filter>
          </defs>
          <path class="ink-brush-loader__bloom" d="M83 22 C113 23 137 47 138 76 C139 111 112 137 78 138 C45 139 22 113 23 80 C24 48 49 22 83 22" />
          <path class="ink-brush-loader__stroke" d="M83 22 C113 23 137 47 138 76 C139 111 112 137 78 138 C45 139 22 113 23 80 C24 48 49 22 83 22" />
          <path class="ink-brush-loader__grain ink-brush-loader__grain--a" d="M106 30 C123 40 134 56 136 74" />
          <path class="ink-brush-loader__grain ink-brush-loader__grain--b" d="M49 129 C34 119 24 101 24 82" />
          <path class="ink-brush-loader__grain ink-brush-loader__grain--c" d="M68 23 C52 28 38 39 30 54" />
        </svg>
      </div>
      <p v-if="text" class="ink-brush-loader__text">{{ text }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import splashUrl from '../assets/splash-ink.png'

withDefaults(defineProps<{
  text?: string
  size?: 'small' | 'medium' | 'large'
  overlay?: boolean
}>(), {
  text: '',
  size: 'medium',
  overlay: false,
})

const imageReady = ref(false)
const brandVisible = ref(false)
const subtitleVisible = ref(false)

function onImageLoad() {
  imageReady.value = true
}

onMounted(() => {
  // Staggered entrance: brand at 400ms, subtitle at 800ms
  setTimeout(() => { brandVisible.value = true }, 400)
  setTimeout(() => { subtitleVisible.value = true }, 800)
})
</script>

<style scoped>
/* ══════════════════════════════════════════════════════════════
   Overlay mode — full-screen splash
   ══════════════════════════════════════════════════════════════ */
.ink-brush-loader--overlay {
  position: fixed;
  inset: 0;
  z-index: 1200;
  width: 100vw;
  height: 100vh;
  background: var(--ink-0);
  display: flex;
  align-items: center;
  justify-content: center;
}

.splash-stage {
  position: relative;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.splash-image {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: 0;
  transform: scale(1.06);
  transition: opacity 800ms var(--ease-out), transform 1400ms var(--ease-out);
}
.splash-image--loaded {
  opacity: 0.35;
  transform: scale(1);
}

.splash-overlay {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(ellipse at 50% 45%, transparent 20%, rgba(12, 13, 16, 0.6) 70%),
    linear-gradient(to bottom, rgba(12, 13, 16, 0.3) 0%, transparent 40%, transparent 60%, rgba(12, 13, 16, 0.7) 100%);
  pointer-events: none;
}

/* Brand group */
.splash-brand {
  position: relative;
  display: flex;
  align-items: center;
  gap: 16px;
  opacity: 0;
  transform: translateY(12px);
  transition: opacity 600ms var(--ease-out), transform 600ms var(--ease-out);
}
.splash-brand--visible {
  opacity: 1;
  transform: translateY(0);
}

.splash-pillar {
  width: 4px;
  height: 52px;
  background: var(--accent-0);
  border-radius: 2px;
  flex-shrink: 0;
}

.splash-title {
  font-family: var(--font-serif-zh);
  font-size: 64px;
  font-weight: 700;
  color: var(--c-text-0);
  letter-spacing: var(--tracking-display);
  line-height: 1;
  text-shadow: 0 2px 20px rgba(0, 0, 0, 0.4);
}

.splash-subtitle {
  font-family: 'EB Garamond', serif;
  font-style: italic;
  font-size: 20px;
  color: var(--c-text-3);
  letter-spacing: 0.02em;
  margin-top: 12px;
  opacity: 0;
  transform: translateY(8px);
  transition: opacity 500ms var(--ease-out), transform 500ms var(--ease-out);
}
.splash-subtitle--visible {
  opacity: 1;
  transform: translateY(0);
}

/* ══════════════════════════════════════════════════════════════
   Non-overlay mode — compact inline loader
   ══════════════════════════════════════════════════════════════ */
.ink-brush-loader {
  --ink-size: 148px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.ink-brush-loader--small { --ink-size: 96px; }
.ink-brush-loader--medium { --ink-size: 148px; }
.ink-brush-loader--large { --ink-size: 176px; }

.ink-brush-loader__panel {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  padding: 18px 22px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 22px;
  background: rgba(18, 19, 27, 0.36);
  box-shadow: 0 28px 72px rgba(0, 0, 0, 0.24);
  color: rgba(232, 233, 240, 0.88);
}

.ink-brush-loader__stage {
  position: relative;
  width: var(--ink-size);
  height: var(--ink-size);
}

.ink-brush-loader__ring {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  color: rgba(232, 233, 240, 0.88);
  overflow: visible;
}

.ink-brush-loader__stroke,
.ink-brush-loader__bloom,
.ink-brush-loader__grain {
  fill: none;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.ink-brush-loader__stroke {
  stroke: url(#inkTone);
  stroke-width: 9.5;
  stroke-dasharray: 372;
  stroke-dashoffset: 372;
  animation: ink-draw 2.45s cubic-bezier(0.62, 0, 0.24, 1) infinite;
}

.ink-brush-loader__bloom {
  stroke: currentColor;
  stroke-width: 12.5;
  opacity: 0;
  filter: url(#inkBloom);
  animation: ink-bloom 2.45s ease-in-out infinite;
}

.ink-brush-loader__grain {
  stroke: currentColor;
  stroke-width: 3.6;
  opacity: 0;
  stroke-dasharray: 78;
  stroke-dashoffset: 78;
  animation: ink-grain 2.45s ease-in-out infinite;
}

.ink-brush-loader__grain--a { animation-delay: 0.22s; }
.ink-brush-loader__grain--b { animation-delay: 0.54s; stroke-width: 4.4; }
.ink-brush-loader__grain--c { animation-delay: 0.78s; stroke-width: 2.8; }

.ink-brush-loader__text {
  color: rgba(202, 205, 222, 0.72);
  font-size: 13px;
  letter-spacing: 0;
  line-height: 1.5;
  user-select: none;
}

@keyframes ink-draw {
  0%   { stroke-dashoffset: 372; opacity: 0; }
  9%   { opacity: 0.96; }
  68%  { stroke-dashoffset: 0; opacity: 0.96; }
  84%  { stroke-dashoffset: 0; opacity: 0.82; }
  100% { stroke-dashoffset: 0; opacity: 0; }
}

@keyframes ink-bloom {
  0%, 50% { opacity: 0; }
  70%     { opacity: 0.2; }
  86%     { opacity: 0.33; }
  100%    { opacity: 0; }
}

@keyframes ink-grain {
  0%, 28% { stroke-dashoffset: 78; opacity: 0; }
  58%     { stroke-dashoffset: 0; opacity: 0.24; }
  86%     { stroke-dashoffset: 0; opacity: 0.12; }
  100%    { opacity: 0; }
}

@media (prefers-reduced-motion: reduce) {
  .splash-image { transition: none; opacity: 0.35; transform: none; }
  .splash-brand, .splash-subtitle { transition: none; opacity: 1; transform: none; }
  .ink-brush-loader__stroke { animation: none; stroke-dashoffset: 0; opacity: 0.78; }
  .ink-brush-loader__bloom  { animation: none; opacity: 0.16; }
  .ink-brush-loader__grain  { animation: none; stroke-dashoffset: 0; opacity: 0.16; }
}

/* Light mode splash */
:global([data-theme="light"]) .ink-brush-loader--overlay { background: var(--paper-0); }
:global([data-theme="light"]) .splash-overlay {
  background:
    radial-gradient(ellipse at 50% 45%, transparent 20%, rgba(240, 235, 224, 0.5) 70%),
    linear-gradient(to bottom, rgba(240, 235, 224, 0.3) 0%, transparent 40%, transparent 60%, rgba(240, 235, 224, 0.6) 100%);
}
:global([data-theme="light"]) .splash-title { color: var(--c-text-0); text-shadow: 0 2px 20px rgba(255, 255, 255, 0.4); }
:global([data-theme="light"]) .ink-brush-loader__panel {
  background: rgba(255, 255, 255, 0.85);
  border-color: var(--c-surface-3);
  color: var(--c-text-0);
  box-shadow: var(--elevation-3);
}
:global([data-theme="light"]) .ink-brush-loader__ring { color: var(--c-text-2); }
:global([data-theme="light"]) .ink-brush-loader__text { color: var(--c-text-2); }
</style>
