<template>
  <div class="session-list" v-if="sessions.length > 0">
    <div class="session-list-header">
      <span class="header-title">Sessions</span>
      <button class="refresh-btn" @click="fetchSessions" :disabled="loading" title="Refresh">↻</button>
    </div>
    <div
      v-for="s in sessions"
      :key="s.id"
      class="session-item"
      :class="{ resumable: isResumable(s) }"
      @click="resumeSession(s)"
    >
      <div class="session-main">
        <span class="session-query">{{ truncate(s.query || s.id, 40) }}</span>
        <span class="session-badge" :class="stateClass(s.state)">{{ s.state }}</span>
      </div>
      <div class="session-meta">
        <span>{{ s.tasks_done }}/{{ s.tasks_total }} tasks</span>
        <span v-if="s.updated_at" class="session-time">{{ formatTime(s.updated_at) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import type { AgentSessionInfo } from '../types'
import { API_BASE } from '../utils/api'

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
  border-left: 1px solid var(--border-color, #e0e0e0);
  background: var(--bg-secondary, #f8f9fa);
  width: 220px;
  overflow-y: auto;
  font-size: 13px;
}
.session-list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  font-weight: 600;
  border-bottom: 1px solid var(--border-color, #e0e0e0);
}
.refresh-btn {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 16px;
  opacity: 0.6;
}
.refresh-btn:hover { opacity: 1; }
.refresh-btn:disabled { opacity: 0.3; cursor: default; }
.session-item {
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-color, #eee);
  cursor: default;
}
.session-item.resumable {
  cursor: pointer;
}
.session-item.resumable:hover {
  background: var(--bg-hover, rgba(0,0,0,0.04));
}
.session-main {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 6px;
}
.session-query {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}
.session-badge {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
  text-transform: uppercase;
  white-space: nowrap;
}
.session-badge.done { background: #d4edda; color: #155724; }
.session-badge.aborted { background: #f8d7da; color: #721c24; }
.session-badge.executing { background: #cce5ff; color: #004085; }
.session-badge.idle { background: #fff3cd; color: #856404; }
.session-meta {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: var(--text-secondary, #888);
  margin-top: 2px;
}
</style>
