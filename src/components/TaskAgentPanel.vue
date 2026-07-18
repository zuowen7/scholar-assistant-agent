<template>
  <aside class="task-agent-panel">
    <div class="task-panel-header">
      <div><Sparkles :size="18" /><strong>{{ t('taskAgent.title') }}</strong></div>
      <StatusBadge tone="accent">Agent V2</StatusBadge>
    </div>

    <div class="task-panel-scroll">
      <section class="task-section current-task">
        <span class="section-label">{{ t('taskAgent.currentTask') }}</span>
        <strong>{{ currentTask || t('taskAgent.waiting') }}</strong>
        <p>{{ scopeText }}</p>
      </section>

      <section class="task-section">
        <div class="section-heading"><span class="section-label">{{ t('taskAgent.steps') }}</span><span>{{ completedSteps }}/{{ taskSteps.length || 0 }}</span></div>
        <div v-if="taskSteps.length" class="task-steps">
          <div v-for="(step, index) in taskSteps" :key="`${step.label}-${index}`" class="task-step" :class="step.status">
            <span class="step-icon"><Check v-if="step.status === 'done'" :size="12" /><LoaderCircle v-else-if="step.status === 'running'" :size="12" /><span v-else /></span>
            <span>{{ step.label }}</span>
          </div>
        </div>
        <p v-else class="task-muted">{{ t('taskAgent.stepsEmpty') }}</p>
      </section>

      <AgentApprovalInline
        v-if="pendingApproval"
        :pending="pendingApproval"
        @decide="decision => sendApproval(pendingApproval!.event_id, decision)"
      />

      <section v-if="latestResponse" class="task-section result-section">
        <span class="section-label">{{ t('taskAgent.result') }}</span>
        <p>{{ latestResponse }}</p>
      </section>
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
          <button type="button" @click="quickTask(t('taskAgent.polishPrompt'))">{{ t('editor.polish') }}</button>
          <button type="button" @click="quickTask(t('taskAgent.argumentPrompt'))">{{ t('editor.checkArgument') }}</button>
        </div>
        <button type="button" class="send-button" :disabled="!input.trim() || sending" @click="submit">
          <LoaderCircle v-if="sending" :size="15" class="spin" /><ArrowUp v-else :size="16" />
        </button>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowUp, Check, LoaderCircle, Sparkles } from 'lucide-vue-next'
import { useAgentChat } from '../composables/useAgentChat'
import { useFileTree } from '../composables/useFileTree'
import AgentApprovalInline from './AgentApprovalInline.vue'
import StatusBadge from './shell/StatusBadge.vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps<{ context: string; selection?: string; activeFile?: string | null }>()
const { rootDir, refresh } = useFileTree()
const { messages, sending, pendingApproval, sendMessage, sendApproval } = useAgentChat()
const input = ref('')

const currentTask = computed(() => [...messages.value].reverse().find(message => message.role === 'user')?.content || '')
const assistantMessage = computed(() => [...messages.value].reverse().find(message => message.role === 'assistant'))
const latestResponse = computed(() => assistantMessage.value?.content?.trim() || '')
const scopeText = computed(() => props.selection
  ? t('taskAgent.selectionScope', { count: props.selection.length })
  : props.activeFile ? t('taskAgent.fileScope', { file: props.activeFile.split(/[\\/]/).pop() }) : t('taskAgent.documentScope'))

const taskSteps = computed(() => {
  const events = assistantMessage.value?.events ?? []
  const steps: Array<{ label: string; status: 'done' | 'running' | 'pending' }> = []
  for (const event of events) {
    if (event.type === 'task_started') {
      steps.push({ label: String(event.metadata?.title || event.content || t('taskAgent.analyzeTask')), status: 'running' })
    } else if (event.type === 'tool_call') {
      const tool = String(event.metadata?.tool_name || event.metadata?.tool || event.content || t('taskAgent.executeTool'))
      steps.push({ label: toolLabel(tool), status: 'running' })
    } else if (event.type === 'tool_result') {
      const tool = String(event.metadata?.tool_name || event.metadata?.tool || '')
      const match = [...steps].reverse().find(step => step.status === 'running' && (!tool || step.label === toolLabel(tool)))
      if (match) match.status = event.metadata?.error ? 'pending' : 'done'
    } else if (event.type === 'task_done') {
      const match = [...steps].reverse().find(step => step.status === 'running')
      if (match) match.status = 'done'
    }
  }
  if (sending.value && !steps.length) steps.push({ label: t('taskAgent.understandContext'), status: 'running' })
  return steps.slice(-5)
})
const completedSteps = computed(() => taskSteps.value.filter(step => step.status === 'done').length)

function toolLabel(tool: string) {
  const labels: Record<string, string> = {
    read_file: t('taskAgent.tools.readFile'), write_file: t('taskAgent.tools.writeFile'), str_replace: t('taskAgent.tools.replace'),
    grep_files: t('taskAgent.tools.grep'), glob_files: t('taskAgent.tools.glob'), run_command: t('taskAgent.tools.command'),
    rag_search: t('taskAgent.tools.rag'), web_search: t('taskAgent.tools.webSearch'), web_fetch: t('taskAgent.tools.webFetch'),
  }
  return labels[tool] || tool
}

async function submit() {
  const task = input.value.trim()
  if (!task || sending.value) return
  input.value = ''
  await sendMessage(task, props.selection || props.context, '', rootDir.value || undefined, props.activeFile || undefined)
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
.task-panel-scroll { flex: 1; min-height: 0; overflow: auto; padding: 14px; }
.task-section { padding: 14px; border: 1px solid var(--c-border); border-radius: 10px; background: var(--c-panel); margin-bottom: 12px; }
.section-label { display: block; margin-bottom: 9px; color: var(--c-text-3); font-size: 11px; font-weight: 650; letter-spacing: .02em; }
.current-task strong { display: block; color: var(--c-text-0); font-size: 13px; line-height: 1.5; }.current-task p,.result-section p{margin:8px 0 0;color:var(--c-text-2);font-size:12px;line-height:1.65;white-space:pre-wrap}
.section-heading { display: flex; justify-content: space-between; color: var(--c-text-3); font-size: 11px; }.section-heading .section-label{margin:0}
.task-steps { display: grid; gap: 9px; margin-top: 12px; }.task-step{display:flex;align-items:center;gap:9px;color:var(--c-text-2);font-size:12px}.task-step.done{color:var(--c-text-1)}.task-step.running{color:var(--c-accent)}
.step-icon { width: 17px; height: 17px; display: grid; place-items: center; border: 1px solid var(--c-border); border-radius: 50%; }.done .step-icon{color:var(--c-success);border-color:var(--c-success-border);background:var(--c-success-bg)}.running .step-icon{border-color:#CDD2FF;background:var(--c-accent-soft)}
.task-muted{margin:12px 0 0;color:var(--c-text-3);font-size:12px;line-height:1.6}.result-section{background:var(--c-surface-2)}
.task-composer { flex: 0 0 auto; margin: 0 12px 12px; padding: 10px; border: 1px solid var(--c-border); border-radius: 10px; background: var(--c-panel); box-shadow: 0 3px 12px rgba(56,48,35,.06); }
.task-composer:focus-within { border-color: #C9CEFF; box-shadow: 0 0 0 3px var(--c-accent-soft); }
.task-composer textarea { width: 100%; resize: none; border: 0; outline: 0; background: transparent; color: var(--c-text-0); font: 12px/1.55 var(--font-sans), var(--font-zh); }
.composer-actions { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-top: 8px; }.quick-actions{display:flex;gap:5px}.quick-actions button{height:25px;padding:0 8px;border:1px solid var(--c-border);border-radius:6px;background:var(--c-panel);color:var(--c-text-2);font-size:10px;cursor:pointer}.quick-actions button:hover{color:var(--c-accent);border-color:#CDD2FF}
.send-button { width: 32px; height: 32px; display: grid; place-items: center; border: 0; border-radius: 8px; background: var(--c-accent); color: #fff; cursor: pointer; }.send-button:disabled{opacity:.45;cursor:default}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
</style>
