<template>
  <aside class="task-agent-panel">
    <div class="task-panel-header">
      <div><Sparkles :size="18" /><strong>{{ t('taskAgent.title') }}</strong></div>
      <div class="task-header-actions">
        <StatusBadge tone="accent">Agent V2</StatusBadge>
        <button
          type="button"
          class="new-task-button"
          data-testid="agent-new-task"
          :title="t('taskAgent.newTask')"
          :disabled="sending || !!pendingApproval"
          @click="startNewWorkflow"
        ><Plus :size="15" /></button>
      </div>
    </div>

    <div class="context-ledger" data-testid="agent-context-ledger">
      <span class="context-file"><FileText :size="13" />{{ activeFileName }}</span>
      <span class="context-scope" :class="{ selected: !!selection }">{{ scopeText }}</span>
    </div>

    <div class="task-panel-scroll">
      <section class="task-section current-task">
        <span class="section-label">{{ t('taskAgent.currentTask') }}</span>
        <strong>{{ currentTask || t('taskAgent.waiting') }}</strong>
        <p>{{ scopeText }}</p>
      </section>

      <section v-if="messages.length" class="conversation-stream" data-testid="agent-conversation">
        <article v-for="message in messages.slice(-8)" :key="message.id" class="conversation-message" :class="message.role">
          <span class="message-role">{{ message.role === 'user' ? t('taskAgent.you') : 'Agent' }}</span>
          <p v-if="message.content">{{ message.content }}</p>
          <div v-if="message.role === 'assistant' && message.events.length" class="message-events">
            <span v-for="(event, index) in visibleEvents(message.events)" :key="`${event.type}-${index}`">
              <Check v-if="event.type === 'tool_result' && !event.metadata?.error" :size="11" />
              <LoaderCircle v-else-if="event.type === 'tool_call'" :size="11" />
              {{ eventLabel(event) }}
            </span>
          </div>
        </article>
      </section>

      <section class="task-section">
        <div class="section-heading">
          <span class="section-label">{{ t('taskAgent.steps') }}</span
          ><span>{{ completedSteps }}/{{ taskSteps.length || 0 }}</span>
        </div>
        <div v-if="taskSteps.length" class="task-steps">
          <div
            v-for="(step, index) in taskSteps"
            :key="`${step.label}-${index}`"
            class="task-step"
            :class="step.status"
          >
            <span class="step-icon"
              ><Check v-if="step.status === 'done'" :size="12" /><LoaderCircle
                v-else-if="step.status === 'running'"
                :size="12" /><span v-else
            /></span>
            <span>{{ step.label }}</span>
          </div>
        </div>
        <p v-else class="task-muted">{{ t('taskAgent.stepsEmpty') }}</p>
      </section>

      <AgentApprovalInline
        v-if="pendingApproval"
        :pending="pendingApproval"
        @decide="(decision) => sendApproval(pendingApproval!.event_id, decision)"
      />

    </div>

    <div class="task-composer">
      <textarea
        v-model="input"
        rows="2"
        :disabled="sending"
        :placeholder="selection ? t('taskAgent.selectionPlaceholder') : t('taskAgent.placeholder')"
        @keydown.enter.exact.prevent="submit"
      />
      <div class="composer-actions">
        <div class="quick-actions">
          <button type="button" @click="quickTask(t('taskAgent.polishPrompt'))">
            {{ t('editor.polish') }}
          </button>
          <button type="button" @click="quickTask(t('taskAgent.argumentPrompt'))">
            {{ t('editor.checkArgument') }}
          </button>
        </div>
        <button
          type="button"
          class="send-button"
          :disabled="!input.trim() || sending"
          @click="submit"
        >
          <LoaderCircle v-if="sending" :size="15" class="spin" /><ArrowUp v-else :size="16" />
        </button>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ArrowUp, Check, FileText, LoaderCircle, Plus, Sparkles } from 'lucide-vue-next'
import type { AgentEvent } from '../types'
import { useAgentChat } from '../composables/useAgentChat'
import { useFileTree } from '../composables/useFileTree'
import { useEditor } from '../composables/useEditor'
import AgentApprovalInline from './AgentApprovalInline.vue'
import StatusBadge from './shell/StatusBadge.vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps<{ context: string; selection?: string; activeFile?: string | null }>()
const { rootDir, refresh } = useFileTree()
const { reloadOpenTabs } = useEditor()
const { messages, sending, pendingApproval, sendMessage, sendApproval, startNewWorkflow } = useAgentChat()
const input = ref('')

// useAgentChat emits one event for every file checkpoint, including consecutive
// writes in a multi-file turn. Listening to that protocol event avoids deriving
// state from an accumulated message history that can be reset between sessions.
function handleAgentFilesChanged() {
  void refresh()
  void reloadOpenTabs()
}

onMounted(() => window.addEventListener('agent-files-changed', handleAgentFilesChanged))
onUnmounted(() => window.removeEventListener('agent-files-changed', handleAgentFilesChanged))

const currentTask = computed(() => [...messages.value].reverse().find(message => message.role === 'user')?.content || '')
const assistantMessage = computed(() => [...messages.value].reverse().find(message => message.role === 'assistant'))
const activeFileName = computed(() => props.activeFile?.split(/[\\/]/).pop() || t('taskAgent.untitled'))
const scopeText = computed(() => props.selection
  ? t('taskAgent.selectionScope', { count: props.selection.length })
  : props.activeFile ? t('taskAgent.fileScope', { file: props.activeFile.split(/[\\/]/).pop() }) : t('taskAgent.documentScope'))

const taskSteps = computed(() => {
  const events = assistantMessage.value?.events ?? []
  const steps: Array<{ label: string; status: 'done' | 'running' | 'pending' }> = []
  for (const event of events) {
    if (event.type === 'task_started') {
      steps.push({
        label: String(event.metadata?.title || event.content || t('taskAgent.analyzeTask')),
        status: 'running',
      })
    } else if (event.type === 'tool_call') {
      const tool = String(
        event.metadata?.tool_name ||
          event.metadata?.tool ||
          event.content ||
          t('taskAgent.executeTool'),
      )
      steps.push({ label: toolLabel(tool), status: 'running' })
    } else if (event.type === 'tool_result') {
      const tool = String(event.metadata?.tool_name || event.metadata?.tool || '')
      const match = [...steps]
        .reverse()
        .find((step) => step.status === 'running' && (!tool || step.label === toolLabel(tool)))
      if (match) match.status = event.metadata?.error ? 'pending' : 'done'
    } else if (event.type === 'task_done') {
      const match = [...steps].reverse().find((step) => step.status === 'running')
      if (match) match.status = 'done'
    }
  }
  if (sending.value && !steps.length)
    steps.push({ label: t('taskAgent.understandContext'), status: 'running' })
  return steps.slice(-5)
})
const completedSteps = computed(
  () => taskSteps.value.filter((step) => step.status === 'done').length,
)

function visibleEvents(events: AgentEvent[]) {
  return events
    .filter((event) => ['tool_call', 'tool_result', 'warning'].includes(event.type))
    .slice(-4)
}

function eventLabel(event: AgentEvent) {
  if (event.type === 'tool_call' || event.type === 'tool_result') {
    return toolLabel(
      String(event.metadata?.tool_name || event.metadata?.tool || event.content || ''),
    )
  }
  return event.content
}

function visibleEvents(events: AgentEvent[]) {
  return events.filter(event => ['tool_call', 'tool_result', 'warning'].includes(event.type)).slice(-4)
}

function eventLabel(event: AgentEvent) {
  if (event.type === 'tool_call' || event.type === 'tool_result') {
    return toolLabel(String(event.metadata?.tool_name || event.metadata?.tool || event.content || ''))
  }
  return event.content
}

function toolLabel(tool: string) {
  const labels: Record<string, string> = {
    read_file: t('taskAgent.tools.readFile'),
    write_file: t('taskAgent.tools.writeFile'),
    str_replace: t('taskAgent.tools.replace'),
    grep_files: t('taskAgent.tools.grep'),
    glob_files: t('taskAgent.tools.glob'),
    run_command: t('taskAgent.tools.command'),
    rag_search: t('taskAgent.tools.rag'),
    web_search: t('taskAgent.tools.webSearch'),
    web_fetch: t('taskAgent.tools.webFetch'),
  }
  return labels[tool] || tool
}

async function submit() {
  const task = input.value.trim()
  if (!task || sending.value) return
  input.value = ''
  await sendMessage(
    task,
    props.selection || props.context,
    '',
    rootDir.value || undefined,
    props.activeFile || undefined,
  )
  refresh()
}

function quickTask(task: string) {
  input.value = task
  submit()
}
</script>

<style scoped>
.task-agent-panel { height: 100%; min-height: 0; display: flex; flex-direction: column; border-left: 1px solid var(--c-border); background: var(--c-panel); }
.task-panel-header { height: 54px; flex: 0 0 54px; display: flex; align-items: center; justify-content: space-between; padding: 0 16px; border-bottom: 1px solid var(--c-border); }
.task-panel-header > div { display: flex; align-items: center; gap: 8px; color: var(--c-text-0); }.task-panel-header svg{color:var(--c-accent)}
.task-panel-header strong { font-size: 14px; }
.task-header-actions { display: flex; align-items: center; gap: 7px; }
.new-task-button { width: 28px; height: 28px; display: grid; place-items: center; border: 1px solid var(--c-border); border-radius: 7px; background: var(--c-panel); color: var(--c-text-2); cursor: pointer; }.new-task-button:hover{color:var(--c-accent);background:var(--c-accent-soft)}.new-task-button:disabled{opacity:.45;cursor:default}
.context-ledger { min-height: 38px; display: flex; align-items: center; gap: 7px; padding: 6px 14px; border-bottom: 1px solid var(--c-border); background: var(--c-surface-1); color: var(--c-text-2); font-size: 10px; }
.context-file,.context-scope{min-width:0;display:inline-flex;align-items:center;gap:5px;padding:4px 7px;border:1px solid var(--c-border);border-radius:6px;background:var(--c-panel);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.context-file{max-width:48%;color:var(--c-text-1)}.context-file svg{flex:0 0 auto;color:var(--brand-red)}.context-scope{margin-left:auto}.context-scope.selected{border-color:var(--c-accent);color:var(--c-accent);background:var(--c-accent-soft)}
.task-panel-scroll { flex: 1; min-height: 0; overflow: auto; padding: 14px; }
.task-section { padding: 14px; border: 1px solid var(--c-border); border-radius: 10px; background: var(--c-panel); margin-bottom: 12px; }
.section-label { display: block; margin-bottom: 9px; color: var(--c-text-3); font-size: 11px; font-weight: 650; letter-spacing: .02em; }
.current-task strong { display: block; color: var(--c-text-0); font-size: 13px; line-height: 1.5; }.current-task p,.result-section p{margin:8px 0 0;color:var(--c-text-2);font-size:12px;line-height:1.65;white-space:pre-wrap}
.section-heading { display: flex; justify-content: space-between; color: var(--c-text-3); font-size: 11px; }.section-heading .section-label{margin:0}
.task-steps { display: grid; gap: 9px; margin-top: 12px; }.task-step{display:flex;align-items:center;gap:9px;color:var(--c-text-2);font-size:12px}.task-step.done{color:var(--c-text-1)}.task-step.running{color:var(--c-accent)}
.step-icon { width: 17px; height: 17px; display: grid; place-items: center; border: 1px solid var(--c-border); border-radius: 50%; }.done .step-icon{color:var(--c-success);border-color:var(--c-success-border);background:var(--c-success-bg)}.running .step-icon{border-color:#CDD2FF;background:var(--c-accent-soft)}
.task-muted{margin:12px 0 0;color:var(--c-text-3);font-size:12px;line-height:1.6}.result-section{background:var(--c-surface-2)}
.conversation-stream { display: grid; gap: 10px; margin-bottom: 12px; }
.conversation-message { padding: 11px 12px; border: 1px solid var(--c-border); border-radius: 9px; background: var(--c-panel); }
.conversation-message.user { border-left: 3px solid var(--c-accent); }
.conversation-message.assistant { background: var(--c-surface-1); }
.message-role { display: block; margin-bottom: 6px; color: var(--c-text-3); font-size: 10px; font-weight: 650; letter-spacing: .04em; text-transform: uppercase; }
.conversation-message p { margin: 0; color: var(--c-text-1); font-size: 12px; line-height: 1.65; white-space: pre-wrap; overflow-wrap: anywhere; }
.message-events { display: grid; gap: 4px; margin-top: 8px; padding-top: 7px; border-top: 1px solid var(--c-border); }
.message-events span { display: flex; align-items: center; gap: 6px; color: var(--c-text-2); font-size: 10px; }.message-events svg{color:var(--c-success)}
.task-composer { flex: 0 0 auto; margin: 0 12px 12px; padding: 10px; border: 1px solid var(--c-border); border-radius: 10px; background: var(--c-panel); box-shadow: 0 3px 12px rgba(56,48,35,.06); }
.task-composer:focus-within { border-color: #C9CEFF; box-shadow: 0 0 0 3px var(--c-accent-soft); }
.task-composer textarea { width: 100%; resize: none; border: 0; outline: 0; background: transparent; color: var(--c-text-0); font: 12px/1.55 var(--font-sans), var(--font-zh); }
.composer-actions { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-top: 8px; }.quick-actions{display:flex;gap:5px}.quick-actions button{height:25px;padding:0 8px;border:1px solid var(--c-border);border-radius:6px;background:var(--c-panel);color:var(--c-text-2);font-size:10px;cursor:pointer}.quick-actions button:hover{color:var(--c-accent);border-color:#CDD2FF}
.send-button { width: 32px; height: 32px; display: grid; place-items: center; border: 0; border-radius: 8px; background: var(--c-accent); color: #fff; cursor: pointer; }.send-button:disabled{opacity:.45;cursor:default}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
</style>
