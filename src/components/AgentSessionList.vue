<template>
  <div class="session-list">
    <div class="session-list-header">
      <span class="header-title">会话</span>
      <button
        class="refresh-btn u-interactive"
        :class="{ spinning: loading }"
        @click="fetchSessions"
        :disabled="loading"
        title="刷新"
      >↻</button>
    </div>

    <!-- Loading skeleton -->
    <div v-if="loading && sessions.length === 0" class="session-skeletons">
      <div v-for="i in 4" :key="i" class="session-skel-item" :style="{ '--stagger-i': i - 1 }">
        <div class="skel-row">
          <UiSkeleton shape="line" height="11" width="60%" />
          <UiSkeleton shape="line" height="11" width="34px" />
        </div>
        <UiSkeleton shape="line" height="9" width="40%" />
      </div>
    </div>

    <!-- Empty -->
    <div v-else-if="sessions.length === 0" class="session-empty anim-fade-in-up">
      <span class="empty-glyph">◷</span>
      <p>暂无历史会话</p>
    </div>

    <!-- List -->
    <TransitionGroup v-else name="v-list-stagger" tag="div" class="session-items">
      <div
        v-for="(s, idx) in sessions"
        :key="s.id"
        class="session-item u-interactive"
        :class="{ resumable: isResumable(s) }"
        :style="{ '--stagger-i': idx }"
        @click="resumeSession(s)"
        tabindex="0"
        @keydown.enter="resumeSession(s)"
      >
        <div class="session-main">
          <span class="session-query">{{ truncate(s.query || s.id, 40) }}</span>
          <span class="session-badge" :class="stateClass(s.state)">{{ s.state }}</span>
        </div>
        <div class="session-meta">
          <span>{{ s.tasks_done }}/{{ s.tasks_total }} tasks</span>
          <span v-if="s.updated_at" class="session-time">{{ formatTime(s.updated_at) }}</span>
        </div>
        <span v-if="isResumable(s)" class="session-resume-hint">恢复 →</span>
      </div>
    </TransitionGroup>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import type { AgentSessionInfo } from '../types'
import { API_BASE } from '../utils/api'
import UiSkeleton from './ui/UiSkeleton.vue'

const emit = defineEmits<{
  (e: 'resume', sessionId: string): void
}>()

const sessions = ref<AgentSessionInfo[]>([])
const loading = ref(false)

async function fetchSessions() {
  loading.value = true
  try {
    const res = await fetch(`${API_BASE}/api/agent/v2/sessions`)
    if (res.ok) {
      sessions.value = await res.json()
    }
  } catch {
    // Silently fail — sidebar is non-critical
  } finally {
    loading.value = false
  }
}

function isResumable(s: AgentSessionInfo): boolean {
  return !['DONE', 'ABORTED'].includes(s.state)
}

function stateClass(state: string): string {
  if (state === 'DONE') return 'done'
  if (state === 'ABORTED') return 'aborted'
  if (state === 'EXECUTING') return 'executing'
  return 'idle'
}

function truncate(text: string, max: number): string {
  return text.length > max ? text.slice(0, max) + '…' : text
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso)
    const now = new Date()
    const diffMs = now.getTime() - d.getTime()
    const diffMin = Math.floor(diffMs / 60000)
    if (diffMin < 1) return 'just now'
    if (diffMin < 60) return `${diffMin}m ago`
    const diffHr = Math.floor(diffMin / 60)
    if (diffHr < 24) return `${diffHr}h ago`
    return d.toLocaleDateString()
  } catch {
    return ''
  }
}

async function resumeSession(s: AgentSessionInfo) {
  if (!isResumable(s)) return
  emit('resume', s.id)
}

onMounted(fetchSessions)

defineExpose({ fetchSessions })
</script>

<style scoped>
.session-list {
  background: transparent;
  width: 100%;
  height: 100%;
  overflow-y: auto;
  font-size: var(--text-sm);
}
.session-list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-3) var(--space-4);
  font-weight: 600;
  color: var(--c-text-1);
  border-bottom: 1px solid var(--c-glass-border);
  position: sticky;
  top: 0;
  background: var(--c-glass);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  z-index: 2;
}
.header-title { font-size: var(--text-sm); letter-spacing: 0.02em; }
.refresh-btn {
  background: transparent;
  border: 1px solid transparent;
  cursor: pointer;
  font-size: 16px;
  width: 28px; height: 28px;
  display: inline-flex; align-items: center; justify-content: center;
  border-radius: var(--radius-sm);
  color: var(--c-text-2);
}
.refresh-btn:hover:not(:disabled) { color: var(--c-accent); background: var(--c-accent-soft); }
.refresh-btn:focus-visible { outline: none; box-shadow: var(--ring-focus); }
.refresh-btn:disabled { cursor: default; color: var(--c-text-3); }
.refresh-btn.spinning { animation: refresh-spin 0.8s linear infinite; }
@keyframes refresh-spin { to { transform: rotate(360deg); } }

.session-items { display: flex; flex-direction: column; }

.session-item {
  position: relative;
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--c-glass-border);
  cursor: default;
  color: var(--c-text-1);
  border-left: 2px solid transparent;
}
.session-item.resumable { cursor: pointer; }
.session-item.resumable:hover {
  background: var(--c-surface-2);
  border-left-color: var(--c-accent);
}
.session-item.resumable:hover .session-resume-hint { opacity: 1; transform: translateX(0); }
.session-item:focus-visible { outline: none; box-shadow: var(--ring-focus); border-radius: var(--radius-sm); }

.session-main {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-2);
}
.session-query {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  color: var(--c-text-0);
}
.session-badge {
  font-size: var(--text-xs);
  padding: 1px 6px;
  border-radius: var(--radius-pill);
  text-transform: uppercase;
  white-space: nowrap;
  font-weight: 600;
}
.session-badge.done { background: var(--c-success-bg); color: var(--c-success); }
.session-badge.aborted { background: var(--c-danger-bg); color: var(--c-danger); }
.session-badge.executing {
  background: var(--c-info-bg); color: var(--c-info);
  animation: badge-pulse 1.6s ease-in-out infinite;
}
@keyframes badge-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.55; }
}
.session-badge.idle { background: var(--c-warn-bg); color: var(--c-warn); }
.session-meta {
  display: flex;
  justify-content: space-between;
  font-size: var(--text-xs);
  color: var(--c-text-2);
  margin-top: 3px;
}

.session-resume-hint {
  position: absolute;
  right: var(--space-4);
  bottom: var(--space-3);
  font-size: var(--text-xs);
  color: var(--c-accent);
  font-weight: 600;
  opacity: 0;
  transform: translateX(-4px);
  transition: opacity var(--motion-base) var(--ease-out), transform var(--motion-base) var(--ease-out);
  pointer-events: none;
}

/* Skeletons */
.session-skeletons { display: flex; flex-direction: column; }
.session-skel-item {
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--c-glass-border);
  display: flex; flex-direction: column; gap: 6px;
  animation: anim-fade-in-up var(--motion-slow) var(--ease-out) both;
  animation-delay: calc(var(--stagger-i, 0) * var(--motion-stagger));
}
.skel-row { display: flex; justify-content: space-between; gap: var(--space-2); }

/* Empty */
.session-empty {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: var(--space-2);
  padding: var(--space-7) var(--space-4);
  color: var(--c-text-3);
  text-align: center;
}
.empty-glyph { font-size: 28px; opacity: 0.6; }
.session-empty p { font-size: var(--text-sm); margin: 0; }

@media (prefers-reduced-motion: reduce) {
  .refresh-btn.spinning, .session-badge.executing, .session-skel-item { animation: none; }
}
</style>
