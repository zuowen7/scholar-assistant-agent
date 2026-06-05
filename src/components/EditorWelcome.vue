<template>
  <div class="editor-welcome">
    <!-- Watermark background -->
    <div class="welcome-watermark" aria-hidden="true">研墨</div>

    <div class="welcome-content">
      <!-- Hero: serif title -->
      <div class="welcome-hero anim-fade-in-up">
        <div class="hero-pillar" />
        <div class="hero-text">
          <h1 class="hero-title">{{ t('editor.welcomeTitle') }}</h1>
          <p class="hero-subtitle">Where research takes form.</p>
        </div>
      </div>

      <!-- Magazine asymmetric grid -->
      <div class="magazine-grid">
        <button class="wc-card wc-card--hero anim-fade-in-up anim-stagger" :style="{ '--stagger-i': 0 }" data-test="card-new-project" @click="$emit('new-project')">
          <div class="wc-card-line" />
          <div class="wc-card-inner">
            <span class="wc-icon accent"><FolderPlus :size="18" /></span>
            <div class="wc-text">
              <strong>{{ t("editor.newProjectStrong") }}</strong>
              <span>{{ t("editor.newProjectSubStrong") }}</span>
            </div>
          </div>
        </button>

        <button class="wc-card anim-fade-in-up anim-stagger" :style="{ '--stagger-i': 1 }" @click="$emit('open-template')">
          <div class="wc-card-line" />
          <div class="wc-card-inner">
            <span class="wc-icon accent"><FileText :size="18" /></span>
            <div class="wc-text">
              <strong>{{ t("editor.fromTemplateStrong") }}</strong>
              <span>{{ t("editor.fromTemplateSubStrong") }}</span>
            </div>
          </div>
        </button>

        <button class="wc-card anim-fade-in-up anim-stagger" :style="{ '--stagger-i': 2 }" data-test="card-open-folder" @click="$emit('open-folder')">
          <div class="wc-card-line" />
          <div class="wc-card-inner">
            <span class="wc-icon"><FolderOpen :size="18" /></span>
            <div class="wc-text">
              <strong>{{ t("editor.openFolderStrong") }}</strong>
              <span>{{ t("editor.openFolderSubStrong") }}</span>
            </div>
          </div>
        </button>

        <button class="wc-card anim-fade-in-up anim-stagger" :style="{ '--stagger-i': 3 }" @click="$emit('new-document')">
          <div class="wc-card-line" />
          <div class="wc-card-inner">
            <span class="wc-icon"><FilePlus :size="18" /></span>
            <div class="wc-text">
              <strong>{{ t("editor.blankDocStrong") }}</strong>
              <span>{{ t("editor.blankDocSubStrong") }}</span>
            </div>
          </div>
        </button>
      </div>

      <!-- Recent projects -->
      <div v-if="recentProjects.length" data-test="recent-projects" class="recent-section">
        <div class="recent-header anim-fade-in-up anim-stagger" :style="{ '--stagger-i': 4 }">{{ t('project.recentProjects') }}</div>
        <div class="recent-list">
          <button
            v-for="(proj, ri) in recentProjects.slice(0, 5)"
            :key="proj.path"
            data-test="recent-item"
            class="recent-item anim-fade-in-up anim-stagger"
            :style="{ '--stagger-i': 5 + ri }"
            @click="$emit('open-recent', proj.path)"
          >
            <span class="recent-name">{{ proj.name }}</span>
            <span class="recent-path">{{ formatPath(proj.path) }}</span>
          </button>
        </div>
      </div>

      <!-- Shortcuts as chips -->
      <div class="welcome-shortcuts">
        <span class="shortcut-chip anim-fade-in-up anim-stagger" :style="{ '--stagger-i': 10 }">
          <kbd class="kbd">Ctrl+K</kbd>
          <span>{{ t("editor.aiEditShortcut") }}</span>
        </span>
        <span class="shortcut-chip anim-fade-in-up anim-stagger" :style="{ '--stagger-i': 11 }">
          <kbd class="kbd">Ctrl+S</kbd>
          <span>{{ t("editor.saveShortcut") }}</span>
        </span>
        <span class="shortcut-chip anim-fade-in-up anim-stagger" :style="{ '--stagger-i': 12 }">
          <kbd class="kbd">Tab</kbd>
          <span>{{ t("editor.acceptCompletion") }}</span>
        </span>
        <span class="shortcut-chip anim-fade-in-up anim-stagger" :style="{ '--stagger-i': 13 }">
          <kbd class="kbd">Ctrl+B</kbd>
          <span>{{ t("editor.fileTree") }}</span>
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { FileText, FolderOpen, FilePlus, FolderPlus } from './ui/icons'
import { useI18n } from 'vue-i18n'
import { onMounted } from 'vue'
import { useProject } from '../composables/useProject'

const { t } = useI18n()
const { recentProjects, loadRecentProjects } = useProject()

onMounted(() => { loadRecentProjects() })

defineEmits<{
  'new-project': []
  'open-template': []
  'open-folder': []
  'new-document': []
  'open-recent': [path: string]
}>()

function formatPath(p: string | undefined | null): string {
  if (!p || typeof p !== 'string') return ''
  const parts = p.split(/[/\\]/)
  return parts.slice(-2).join('/')
}
</script>

<style scoped>
.editor-welcome {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-7) var(--space-6);
  background: var(--editor-bg);
  overflow-y: auto;
  position: relative;
}

/* Watermark */
.welcome-watermark {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%) scale(2.5);
  font-family: var(--font-serif-zh);
  font-size: 120px;
  font-weight: 700;
  color: var(--c-text-0);
  opacity: 0.03;
  pointer-events: none;
  user-select: none;
  white-space: nowrap;
}

.welcome-content {
  position: relative;
  width: min(580px, 100%);
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}

/* Hero */
.welcome-hero {
  display: flex;
  align-items: flex-start;
  gap: 16px;
}

.hero-pillar {
  width: 4px;
  height: 48px;
  background: var(--accent-0);
  border-radius: 2px;
  flex-shrink: 0;
  margin-top: 8px;
  transform: scaleY(0);
  transform-origin: top;
  animation: pillar-grow 500ms var(--ease-spring) forwards;
  animation-delay: 120ms;
}
@keyframes pillar-grow {
  to { transform: scaleY(1); }
}

.hero-title {
  margin: 0;
  font-family: var(--font-serif-zh);
  font-size: var(--text-display-lg);
  font-weight: 700;
  color: var(--c-text-0);
  letter-spacing: var(--tracking-display);
  line-height: var(--leading-display);
}

.hero-subtitle {
  margin: 6px 0 0;
  font-family: 'EB Garamond', serif;
  font-style: italic;
  font-size: 18px;
  color: var(--c-text-3);
  letter-spacing: 0.01em;
}

/* Magazine grid */
.magazine-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-2);
}

/* Cards */
.wc-card {
  position: relative;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--c-surface-3);
  border-radius: var(--radius-md);
  background: var(--c-surface-1);
  color: var(--c-text-1);
  cursor: pointer;
  font: inherit;
  text-align: left;
  overflow: hidden;
  transition: border-color var(--motion-fast) var(--ease-out),
              background var(--motion-fast) var(--ease-out);
}

.wc-card-line {
  height: 1px;
  background: linear-gradient(90deg, var(--c-accent-soft), transparent 60%);
  opacity: 0;
  transition: opacity var(--motion-fast) var(--ease-out);
}

.wc-card:hover {
  border-color: var(--c-accent);
  background: var(--c-surface-2);
}
.wc-card:hover .wc-card-line {
  opacity: 1;
  background: linear-gradient(90deg, var(--accent-0), transparent 60%);
}

.wc-card--hero {
  grid-column: 1 / -1;
}

.wc-card--hero .wc-card-inner {
  gap: var(--space-5);
  padding: var(--space-5);
}

.wc-card-inner {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4);
}

.wc-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  background: var(--c-surface-3);
  color: var(--c-text-2);
  flex-shrink: 0;
}
.wc-icon.accent { background: var(--c-accent-soft); color: var(--c-accent); }
.wc-card:hover .wc-icon { background: var(--c-accent-soft); color: var(--c-accent); }

.wc-text { display: flex; flex-direction: column; gap: 3px; }
.wc-text strong { font-size: var(--text-md); font-weight: 600; }
.wc-text span { font-size: var(--text-sm); color: var(--c-text-3); }

/* Recent projects */
.recent-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.recent-header {
  font-size: 12px;
  font-weight: 600;
  color: var(--c-text-3);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.recent-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.recent-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border: 1px solid var(--c-surface-3);
  border-radius: var(--radius-sm);
  background: var(--c-surface-1);
  color: var(--c-text-1);
  font: inherit;
  cursor: pointer;
  text-align: left;
  transition: border-color var(--motion-fast), background var(--motion-fast);
}
.recent-item:hover {
  border-color: var(--c-accent);
  background: var(--c-surface-2);
}

.recent-name {
  font-size: 13px;
  font-weight: 600;
}

.recent-path {
  font-size: 11px;
  color: var(--c-text-3);
  margin-left: auto;
}

/* Shortcut chips */
.welcome-shortcuts {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.shortcut-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: var(--radius-pill);
  background: var(--c-surface-2);
  border: 1px solid var(--c-surface-3);
  font-size: var(--text-sm);
  color: var(--c-text-3);
  transition: background var(--motion-fast), color var(--motion-fast);
}

.shortcut-chip:hover {
  background: var(--c-surface-3);
  color: var(--c-text-1);
}

.kbd {
  display: inline-flex;
  align-items: center;
  height: 20px;
  padding: 0 5px;
  border: 1px solid var(--c-surface-4);
  border-radius: var(--radius-xs);
  background: var(--c-surface-3);
  color: var(--c-text-2);
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1;
}

/* Light mode */
:global([data-theme="light"]) .welcome-watermark { color: var(--c-text-0); opacity: 0.04; }
:global([data-theme="light"]) .wc-card { background: var(--c-surface-1); border-color: var(--c-surface-3); }
:global([data-theme="light"]) .shortcut-chip { background: var(--c-surface-2); }

@media (prefers-reduced-motion: reduce) {
  .hero-pillar { animation: none; transform: none; }
}
</style>
