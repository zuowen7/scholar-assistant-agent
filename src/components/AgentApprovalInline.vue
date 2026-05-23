<template>
  <div v-if="pending" class="approval-bar">
    <div class="approval-header">
      <span class="approval-icon">&#x26A0;</span>
      <span class="approval-label">Agent wants to run</span>
      <code class="approval-tool">{{ pending.tool_name }}</code>
      <span v-if="pending.risk" class="approval-risk" :class="'risk-' + pending.risk">{{ pending.risk }}</span>
    </div>
    <div v-if="pending.reason" class="approval-reason">{{ pending.reason }}</div>
    <div v-if="previewText" class="approval-preview">
      <code class="approval-preview-code">{{ previewText }}</code>
    </div>
    <div class="approval-actions">
      <button class="approval-btn allow-once u-interactive" @click="decide('allow_once')" :disabled="deciding">
        <UiSpinner v-if="deciding && pendingDecision === 'allow_once'" size="sm" />
        <span v-else>仅此一次</span>
      </button>
      <button class="approval-btn allow-session u-interactive" @click="decide('allow_session')" :disabled="deciding">
        <UiSpinner v-if="deciding && pendingDecision === 'allow_session'" size="sm" />
        <span v-else>本次会话</span>
      </button>
      <button class="approval-btn deny u-interactive" @click="decide('deny')" :disabled="deciding">
        <UiSpinner v-if="deciding && pendingDecision === 'deny'" size="sm" />
        <span v-else>拒绝</span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { PendingApproval } from '../composables/useAgentChat'
import UiSpinner from './ui/UiSpinner.vue'

const props = defineProps<{
  pending: PendingApproval | null
}>()

const emit = defineEmits<{
  (e: 'decide', decision: 'allow_once' | 'allow_session' | 'deny'): void
}>()

const deciding = ref(false)
const pendingDecision = ref<'allow_once' | 'allow_session' | 'deny' | null>(null)

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
  if (deciding.value) return
  deciding.value = true
  pendingDecision.value = decision
  emit('decide', decision)
  // 重置由父组件在成功回调中完成; 这里加一个超时兜底
  setTimeout(() => { deciding.value = false; pendingDecision.value = null }, 2000)
}
</script>

<style scoped>
.approval-bar {
  background: color-mix(in srgb, var(--c-warn) 8%, var(--c-surface-1));
  border: 1px solid var(--c-warn);
  border-radius: var(--radius-md);
  padding: 14px 16px;
  margin: 0 16px 8px;
  box-shadow: var(--elevation-3), 0 0 0 4px color-mix(in srgb, var(--c-warn) 12%, transparent);
  animation: approval-pop-in 380ms var(--ease-spring) both;
  position: relative;
  overflow: hidden;
}
/* Attention sweep across the top edge */
.approval-bar::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2px;
  background: linear-gradient(90deg, transparent, var(--c-warn), transparent);
  background-size: 40% 100%;
  background-repeat: no-repeat;
  animation: approval-scan 1.6s ease-in-out infinite;
}
@keyframes approval-pop-in {
  from { opacity: 0; transform: scale(0.94) translateY(-6px); }
  to { opacity: 1; transform: scale(1) translateY(0); }
}
@keyframes approval-scan {
  0% { background-position: -40% 0; }
  100% { background-position: 140% 0; }
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
  animation: approval-warn-blink 1.4s ease-in-out infinite;
}
@keyframes approval-warn-blink {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.55; transform: scale(0.9); }
}
.approval-label {
  font-size: var(--text-sm);
  color: var(--c-text-2);
}
.approval-tool {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--c-accent);
  background: var(--c-accent-soft);
  padding: 1px 6px;
  border-radius: var(--radius-xs);
  font-family: var(--font-mono);
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

.approval-reason {
  font-size: var(--text-xs);
  color: var(--c-warn);
  margin-top: 6px;
  line-height: 1.5;
}
.approval-preview {
  margin-top: 8px;
  background: var(--c-surface-2);
  border: 1px solid var(--c-surface-3);
  border-radius: var(--radius-sm);
  padding: 8px 10px;
  max-height: 120px;
  overflow-y: auto;
}
.approval-preview-code {
  font-size: var(--text-xs);
  font-family: var(--font-mono);
  color: var(--c-text-2);
  white-space: pre-wrap;
  word-break: break-all;
}

.approval-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}
.approval-btn {
  flex: 1;
  min-height: 32px;
  padding: 7px 10px;
  border: none;
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.approval-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.approval-btn:focus-visible { outline: none; box-shadow: var(--ring-focus); }
.allow-once {
  background: var(--c-success);
  color: #fff;
}
.allow-once:hover:not(:disabled) { background: color-mix(in srgb, var(--c-success) 85%, #000); }
.allow-session {
  background: var(--c-accent);
  color: #fff;
}
.allow-session:hover:not(:disabled) { background: var(--c-accent-hover); }
.deny {
  background: var(--c-danger);
  color: #fff;
}
.deny:hover:not(:disabled) { background: color-mix(in srgb, var(--c-danger) 85%, #000); }

@media (prefers-reduced-motion: reduce) {
  .approval-bar, .approval-bar::before, .approval-icon { animation: none; }
}
</style>
