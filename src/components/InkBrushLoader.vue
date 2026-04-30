<template>
  <div
    class="ink-brush-loader"
    :class="[`ink-brush-loader--${size}`, { 'ink-brush-loader--overlay': overlay }]"
    role="status"
    aria-live="polite"
    :aria-label="text"
  >
    <div class="ink-brush-loader__panel">
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
              <feColorMatrix
                in="blur"
                type="matrix"
                values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 .48 0"
              />
            </filter>
          </defs>

          <path
            class="ink-brush-loader__bloom"
            d="M83 22 C113 23 137 47 138 76 C139 111 112 137 78 138 C45 139 22 113 23 80 C24 48 49 22 83 22"
          />
          <path
            class="ink-brush-loader__stroke"
            d="M83 22 C113 23 137 47 138 76 C139 111 112 137 78 138 C45 139 22 113 23 80 C24 48 49 22 83 22"
          />
          <path
            class="ink-brush-loader__grain ink-brush-loader__grain--a"
            d="M106 30 C123 40 134 56 136 74"
          />
          <path
            class="ink-brush-loader__grain ink-brush-loader__grain--b"
            d="M49 129 C34 119 24 101 24 82"
          />
          <path
            class="ink-brush-loader__grain ink-brush-loader__grain--c"
            d="M68 23 C52 28 38 39 30 54"
          />
        </svg>

        <div class="ink-brush-loader__brush">
          <svg viewBox="0 0 46 46">
            <path class="ink-brush-loader__handle" d="M27 3 L34 10 L19 28 L13 23 Z" />
            <path class="ink-brush-loader__ferrule" d="M16 22 L22 28 L17 34 L10 27 Z" />
            <path class="ink-brush-loader__bristle" d="M10 27 C6 31 5 37 8 42 C13 39 17 36 17 34 Z" />
            <path class="ink-brush-loader__bristle-tip" d="M8 42 C9 38 11 35 14 32" />
          </svg>
        </div>
      </div>

      <p v-if="text" class="ink-brush-loader__text">{{ text }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  text?: string
  size?: 'small' | 'medium' | 'large'
  overlay?: boolean
}>(), {
  text: '正在整理思路...',
  size: 'medium',
  overlay: false,
})
</script>

<style scoped>
.ink-brush-loader {
  --ink-size: 148px;
  --ink-color: rgba(25, 25, 30, 0.9);
  --ink-muted: rgba(108, 112, 132, 0.78);
  --ink-panel: rgba(250, 250, 253, 0.72);
  --ink-panel-border: rgba(120, 124, 145, 0.18);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--ink-color);
}

.ink-brush-loader--overlay {
  position: fixed;
  inset: 0;
  z-index: 1200;
  width: 100vw;
  height: 100vh;
  background:
    radial-gradient(circle at 50% 45%, rgba(120, 116, 255, 0.13), transparent 34%),
    rgba(10, 11, 16, 0.74);
  backdrop-filter: blur(14px) saturate(1.08);
  -webkit-backdrop-filter: blur(14px) saturate(1.08);
  color: rgba(238, 239, 245, 0.88);
  --ink-color: rgba(232, 233, 240, 0.88);
  --ink-muted: rgba(202, 205, 222, 0.72);
  --ink-panel: rgba(18, 19, 27, 0.36);
  --ink-panel-border: rgba(255, 255, 255, 0.08);
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
  border: 1px solid var(--ink-panel-border);
  border-radius: 22px;
  background: var(--ink-panel);
  box-shadow: 0 28px 72px rgba(0, 0, 0, 0.24);
}

.ink-brush-loader:not(.ink-brush-loader--overlay) .ink-brush-loader__panel {
  box-shadow: none;
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
  color: var(--ink-color);
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

.ink-brush-loader__brush {
  position: absolute;
  inset: 0;
  opacity: 0;
  animation: brush-trace 2.45s cubic-bezier(0.62, 0, 0.24, 1) infinite;
}

.ink-brush-loader__brush svg {
  position: absolute;
  left: 50%;
  top: 7%;
  width: calc(var(--ink-size) * 0.25);
  height: calc(var(--ink-size) * 0.25);
  overflow: visible;
  transform: translate(-12%, -44%) rotate(42deg);
  filter: drop-shadow(0 6px 10px rgba(0, 0, 0, 0.28));
}

.ink-brush-loader__handle {
  fill: #8a6043;
}

.ink-brush-loader__ferrule {
  fill: #d6c3a3;
}

.ink-brush-loader__bristle {
  fill: currentColor;
}

.ink-brush-loader__bristle-tip {
  fill: none;
  stroke: rgba(255, 255, 255, 0.28);
  stroke-width: 1.2;
  stroke-linecap: round;
}

.ink-brush-loader__text {
  color: var(--ink-muted);
  font-size: 13px;
  letter-spacing: 0;
  line-height: 1.5;
  user-select: none;
}

@keyframes ink-draw {
  0% {
    stroke-dashoffset: 372;
    opacity: 0;
  }
  9% {
    opacity: 0.96;
  }
  68% {
    stroke-dashoffset: 0;
    opacity: 0.96;
  }
  84% {
    stroke-dashoffset: 0;
    opacity: 0.82;
  }
  100% {
    stroke-dashoffset: 0;
    opacity: 0;
  }
}

@keyframes ink-bloom {
  0%, 50% {
    opacity: 0;
  }
  70% {
    opacity: 0.2;
  }
  86% {
    opacity: 0.33;
  }
  100% {
    opacity: 0;
  }
}

@keyframes ink-grain {
  0%, 28% {
    stroke-dashoffset: 78;
    opacity: 0;
  }
  58% {
    stroke-dashoffset: 0;
    opacity: 0.24;
  }
  86% {
    stroke-dashoffset: 0;
    opacity: 0.12;
  }
  100% {
    opacity: 0;
  }
}

@keyframes brush-trace {
  0% {
    opacity: 0;
    transform: rotate(-8deg) scale(0.92);
  }
  8% {
    opacity: 1;
    transform: rotate(8deg) scale(1);
  }
  68% {
    opacity: 1;
    transform: rotate(352deg) scale(1);
  }
  84% {
    opacity: 0;
    transform: rotate(374deg) scale(0.96);
  }
  100% {
    opacity: 0;
    transform: rotate(374deg) scale(0.96);
  }
}

@media (prefers-reduced-motion: reduce) {
  .ink-brush-loader__stroke,
  .ink-brush-loader__bloom,
  .ink-brush-loader__grain,
  .ink-brush-loader__brush {
    animation: none;
  }

  .ink-brush-loader__stroke {
    stroke-dashoffset: 0;
    opacity: 0.78;
  }

  .ink-brush-loader__bloom {
    opacity: 0.16;
  }

  .ink-brush-loader__grain {
    stroke-dashoffset: 0;
    opacity: 0.16;
  }

  .ink-brush-loader__brush {
    display: none;
  }
}
</style>
