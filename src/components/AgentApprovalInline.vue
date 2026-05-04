<template>
  <div v-if="pending" class="approval-bar">
    <div class="approval-header">
      <span class="approval-icon">&#x26A0;</span>
      <span class="approval-label">Agent wants to run</span>
      <code class="approval-tool">{{ pending.tool_name }}</code>
      <span v-if="pending.risk" class="approval-risk" :class="'risk-' + pending.risk">{{ pending.risk }}</span>
    </div>
    <div v-if="previewText" class="approval-preview">
      <code class="approval-preview-code">{{ previewText }}</code>
    </div>
    <div class="approval-actions">
      <button class="approval-btn allow-once" @click="decide('allow_once')" :disabled="deciding">
        Allow once
      </button>
      <button class="approval-btn allow-session" @click="decide('allow_session')" :disabled="deciding">
        Allow session
      </button>
      <button class="approval-btn deny" @click="decide('deny')" :disabled="deciding">
        Deny
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { PendingApproval } from '../composables/useAgentChat'

const props = defineProps<{
  pending: PendingApproval | null
}>()

const emit = defineEmits<{
  (e: 'decide', decision: 'allow_once' | 'allow_session' | 'deny'): void
}>()

const deciding = ref(false)

const previewText = computed(() => {
  if (!props.pending) return ''
  if (props.pending.preview?.diff) return props.pending.preview.diff as string
  if (props.pending.args) {
    const entries = Object.entries(props.pending.args)
    if (entries.length === 0) return ''
    return entries
      .map(([k, v]) => `${k}: ${typeof v === 'string' ? (v.length > 200 ? v.slice(0, 200) + '...' : v) : JSON.stringify(v)}`)
      .join('\n')
  }
  return ''
})

async function decide(decision: 'allow_once' | 'allow_session' | 'deny') {
  deciding.value = true
  emit('decide', decision)
  // 重置由父组件在成功回调中完成; 这里加一个超时兜底
  setTimeout(() => { deciding.value = false }, 2000)
}
</script>

<style scoped>
.approval-bar {
  background: var(--surface);
  border: 1px solid var(--c-warn);
  border-radius: 10px;
  padding: 12px 14px;
  margin-bottom: 8px;
  animation: approval-slide-in 0.2s ease;
}
@keyframes approval-slide-in {
  from { opacity: 0; transform: translateY(-8px); }
  to { opacity: 1; transform: translateY(0); }
}

.approval-header {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.approval-icon {
  font-size: 16px;
  color: var(--c-warn);
}
.approval-label {
  font-size: 13px;
  color: var(--text-secondary);
}
.approval-tool {
  font-size: 13px;
  font-weight: 600;
  color: var(--accent);
  background: var(--hover-bg);
  padding: 1px 6px;
  border-radius: 4px;
}
.approval-risk {
  font-size: 10px;
  text-transform: uppercase;
  padding: 1px 5px;
  border-radius: 3px;
  font-weight: 600;
}
.risk-safe { background: var(--c-success-bg); color: var(--c-success); }
.risk-moderate { background: var(--c-warn-bg); color: var(--c-warn); }
.risk-destructive { background: var(--c-danger-bg); color: var(--c-danger); }
.risk-banned { background: var(--c-danger-bg); color: var(--c-danger); }

.approval-preview {
  margin-top: 8px;
  background: var(--code-bg);
  border-radius: 6px;
  padding: 8px 10px;
  max-height: 120px;
  overflow-y: auto;
}
.approval-preview-code {
  font-size: 11px;
  font-family: monospace;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-all;
}

.approval-actions {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}
.approval-btn {
  flex: 1;
  padding: 7px 10px;
  border: none;
  border-radius: 7px;
  font-size: 12px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: opacity 0.15s;
}
.approval-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.approval-btn:hover:not(:disabled) {
  opacity: 0.85;
}
.allow-once {
  background: var(--c-success);
  color: #fff;
}
.allow-session {
  background: var(--c-accent);
  color: #fff;
}
.deny {
  background: var(--c-danger);
  color: #fff;
}
</style>
