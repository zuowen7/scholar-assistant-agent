<template>
  <div class="ai-chat-panel">
    <!-- Header -->
    <div class="ac-header">
      <div class="ac-title-row">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
        <span class="ac-title">{{ t('aiPanel.title') }}</span>
      </div>
      <div class="ac-header-actions">
        <button class="ac-icon-btn u-interactive" @click="clearHistory" :title="t('aiPanel.clear')" :disabled="messages.length===0||streaming">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 102.13-9.36L1 10"/></svg>
        </button>
        <button class="ac-icon-btn u-interactive" @click="$emit('undo')" :title="t('aiPanel.undo')" :disabled="!canUndo">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7v6h6"/><path d="M21 17a9 9 0 00-15-6.7L3 13"/></svg>
        </button>
        <button class="ac-icon-btn u-interactive" @click="$emit('close')" :title="t('aiPanel.close')">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
        </button>
      </div>
    </div>

    <!-- Context bar -->
    <div class="ac-context" v-if="editorContext">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
      <span>{{ t('aiPanel.contextChars', { count: editorContext.length }) }}</span>
    </div>

    <!-- Thinking scan bar -->
    <div v-if="streaming" class="ac-thinking-bar"></div>

    <!-- Messages -->
    <div class="ac-messages" ref="messagesRef" @click="handleCodeBlockClick">
      <Transition name="v-fade">
        <div v-if="messages.length===0 && !streaming" class="ac-empty">
          <div class="ac-empty-icon anim-pop-in">
            <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2"><circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/></svg>
          </div>
          <p class="ac-empty-title anim-fade-in-up">{{ t('aiPanel.greeting') }}</p>
          <p class="ac-empty-sub anim-fade-in-up" v-html="t('aiPanel.greetingHint', { atChar: '@' })"></p>
        </div>
      </Transition>

      <div v-for="msg in messages" :key="msg.id" class="ac-msg" :class="msg.role">
        <div class="ac-avatar">{{ msg.role==='user'?'U':'AI' }}</div>
        <div class="ac-body">
          <div v-if="msg.role==='user'" class="ac-user-bubble">{{ msg.content }}</div>
          <template v-else>
            <div v-if="msg.thinking" class="ac-thinking">{{ msg.thinking }}</div>
            <div class="ac-ai-bubble" v-html="renderMd(msg.content, msg.id)"></div>
            <div v-if="msg.isStreaming" class="ac-cursor"></div>
            <div v-if="!msg.isStreaming && msg.content" class="ac-actions">
              <button class="ac-action-btn u-interactive" @click="$emit('insert', msg.content)">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
                {{ t('aiPanel.insert') }}
              </button>
              <button class="ac-action-btn u-interactive" :class="{ copied: copiedId === msg.id }" @click="copyText(msg.content, msg.id)">
                <svg v-if="copiedId === msg.id" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
                <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
                {{ copiedId === msg.id ? t('aiPanel.copied') : t('aiPanel.copy') }}
              </button>
            </div>
          </template>
        </div>
      </div>

      <div v-if="streaming" class="ac-msg assistant">
        <div class="ac-avatar">AI</div>
        <div class="ac-body">
          <div v-if="thinkingText" class="ac-thinking">{{ thinkingText }}</div>
          <div v-if="streamContent" class="ac-ai-bubble" v-html="renderMd(streamContent, 'streaming')"></div>
          <div v-if="!streamContent && !thinkingText" class="ac-ai-bubble ac-waiting">
            <span class="dot-wave"><i></i><i></i><i></i></span>
          </div>
          <div class="ac-cursor"></div>
        </div>
      </div>
    </div>

    <!-- Approval bar -->
    <AgentApprovalInline
      v-if="pendingApproval"
      :pending="pendingApproval"
      @decide="handleApprovalDecision"
    />

    <!-- File chips -->
    <div class="ac-attachments" v-if="files.length">
      <TransitionGroup name="v-spring">
        <div class="ac-file u-interactive" v-for="f in files" :key="f.name">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
          <span>{{ f.name }}</span>
          <button class="ac-file-x" :title="t('aiPanel.removeAttachment')" @click="removeFile(f.name)">×</button>
        </div>
      </TransitionGroup>
    </div>

    <!-- Presets -->
    <Transition name="v-slide-up">
      <div class="ac-presets anim-stagger" v-if="!streaming">
        <button class="ac-preset u-interactive" style="--stagger-i:0" @click="sendPreset('polish')">{{ t('aiPanel.presetPolish') }}</button>
        <button class="ac-preset u-interactive" style="--stagger-i:1" @click="sendPreset('expand')">{{ t('aiPanel.presetExpand') }}</button>
        <button class="ac-preset u-interactive" style="--stagger-i:2" @click="sendPreset('review')">{{ t('aiPanel.presetReview') }}</button>
        <button class="ac-preset u-interactive" style="--stagger-i:3" @click="sendPreset('en')">{{ t('aiPanel.presetEn') }}</button>
        <button class="ac-preset u-interactive" style="--stagger-i:4" @click="sendPreset('zh')">{{ t('aiPanel.presetZh') }}</button>
      </div>
    </Transition>

    <!-- Input area -->
    <div class="ac-input-area">
      <button class="ac-attach-btn u-interactive" @click="attachFile" :title="t('aiPanel.addAttachment')" :disabled="streaming">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"/></svg>
      </button>
      <div class="ac-input-wrap">
        <textarea
          ref="inputRef"
          v-model="input"
          class="ac-input"
          :placeholder="t('aiPanel.inputPlaceholder', { atChar: '@' })"
          @keydown.enter.exact.prevent="send"
          @keydown.tab.exact.prevent="acceptSuggestion"
          @keydown.escape="dismissSuggestion"
          @input="onInput"
          :disabled="streaming"
          rows="1"
        />
        <!-- Slash command menu -->
        <Transition name="v-scale-in">
          <div v-if="slashMenu" class="ac-menu ac-slash-menu">
            <div v-for="(cmd, i) in filteredCommands" :key="cmd.cmd" class="ac-menu-item anim-fade-in-up anim-stagger" :style="{ '--stagger-i': i }" @click="applyCommand(cmd)">
              <span class="ac-menu-cmd">{{ cmd.cmd }}</span>
              <span class="ac-menu-desc">{{ cmd.desc }}</span>
            </div>
          </div>
        </Transition>
        <!-- @ reference menu -->
        <Transition name="v-scale-in">
          <div v-if="atMenu" class="ac-menu ac-at-menu">
            <div v-for="(f, i) in filteredFiles" :key="f.name" class="ac-menu-item anim-fade-in-up anim-stagger" :style="{ '--stagger-i': i }" @click="applyFileRef(f)">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
              <span>{{ f.name }}</span>
            </div>
          </div>
        </Transition>
      </div>
      <button
        v-if="panelSpeech.isSupported"
        class="ac-attach-btn u-interactive"
        :class="{ 'voice-active': panelSpeech.status.value === 'listening' }"
        :title="panelSpeech.status.value === 'listening' ? t('aiPanel.voiceStop') : t('aiPanel.voiceStart')"
        :disabled="streaming"
        @click="togglePanelSpeech"
      >
        <Mic :size="16" :stroke-width="2" />
      </button>
      <button
        class="ac-send-btn u-interactive"
        :class="{ stopping: streaming }"
        @click="streaming ? stopStream() : send()"
        :disabled="!streaming && !input.trim()"
        :title="streaming ? t('aiPanel.stopGenerate') : t('aiPanel.send')"
      >
        <svg v-if="streaming" width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
          <rect x="3" y="3" width="18" height="18" rx="3"/>
        </svg>
        <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4z"/></svg>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, watch } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

import DOMPurify from 'dompurify'
import { readSseStream } from '../utils/streamReader'
import { aiMessages, aiStreaming, aiStreamContent, aiThinkingText, aiAbortCtrl } from '../composables/useAiPanelState'
import type { AiPanelMsg } from '../composables/useAiPanelState'
import { API_BASE } from '../utils/api'
import AgentApprovalInline from './AgentApprovalInline.vue'
import type { PendingApproval } from '../composables/useAgentChat'
import { useFileTree } from '../composables/useFileTree'
import { useSpeechRecognition } from '../composables/useSpeechRecognition'
import { Mic } from './ui/icons'

let voiceBaseInput = ''
const panelSpeech = useSpeechRecognition({
  onResult: (text) => { input.value = voiceBaseInput + (voiceBaseInput ? ' ' : '') + text },
})

function togglePanelSpeech() {
  if (panelSpeech.status.value === 'listening') {
    voiceBaseInput = ''
    panelSpeech.stop()
  } else {
    voiceBaseInput = input.value
    panelSpeech.start()
  }
}

const props = defineProps<{
  editorContext: string
  activeFile?: string | null
  canUndo?: boolean
  workspaceFiles?: { name: string; content?: string }[]
}>()

const emit = defineEmits<{
  (e: 'insert', text: string): void
  (e: 'undo'): void
  (e: 'close'): void
}>()

type Msg = AiPanelMsg

interface FileRef { name: string; content: string }

const API = API_BASE

const messages = aiMessages
const streaming = aiStreaming
const streamContent = aiStreamContent
const thinkingText = aiThinkingText

const input = ref('')
const files = ref<FileRef[]>([])
const inputRef = ref<HTMLTextAreaElement>()
const messagesRef = ref<HTMLElement>()
const slashMenu = ref(false)
const atMenu = ref(false)
const copiedId = ref<string | null>(null)
let copiedTimer: ReturnType<typeof setTimeout> | null = null
const acSessionId = ref<string | null>(null)
const pendingApproval = ref<PendingApproval | null>(null)
const { rootDir } = useFileTree()

// ── Slash commands ──────────────────────────────────────────
const commands = [
  { cmd: '/explain', prompt: 'Please explain the following text in detail, breaking down the key concepts:', desc: t('aiPanel.cmd.explain') },
  { cmd: '/fix', prompt: 'Please identify and fix any issues in the following text:', desc: t('aiPanel.cmd.fix') },
  { cmd: '/translate', prompt: 'Please translate the following text:', desc: t('aiPanel.cmd.translate') },
  { cmd: '/polish', prompt: 'Please polish the following academic text, improving grammar, vocabulary and style:', desc: t('aiPanel.cmd.polish') },
  { cmd: '/expand', prompt: 'Please expand the following text with more details and academic depth:', desc: t('aiPanel.cmd.expand') },
  { cmd: '/summarize', prompt: 'Please provide a concise summary of the following text:', desc: t('aiPanel.cmd.summarize') },
  { cmd: '/outline', prompt: 'Please generate a detailed outline for a paper on the following topic:', desc: t('aiPanel.cmd.outline') },
  { cmd: '/review', prompt: 'Please review the following academic text, identify issues and suggest improvements:', desc: t('aiPanel.cmd.review') },
  { cmd: '/rewrite', prompt: 'Please rewrite the following text to improve clarity and flow:', desc: t('aiPanel.cmd.rewrite') },
  { cmd: '/cite', prompt: 'Please generate proper academic citations (IEEE/APA/GB-T) for the following references:', desc: t('aiPanel.cmd.cite') },
]

const filteredCommands = computed(() => {
  const q = input.value.toLowerCase()
  return commands.filter(c => c.cmd.includes(q) || c.desc.toLowerCase().includes(q))
})

const filteredFiles = computed(() => {
  const q = input.value.replace(/.*@/, '').toLowerCase()
  const all = [...files.value, ...(props.workspaceFiles || [])]
  if (!q) return all.slice(0, 20)
  return all.filter(f => f.name.toLowerCase().includes(q)).slice(0, 20)
})

function onInput() {
  const v = input.value
  const pos = inputRef.value?.selectionStart ?? v.length
  const before = v.slice(0, pos)
  const lastWord = before.split(/\s/).pop() || ''
  slashMenu.value = lastWord.startsWith('/') && lastWord.length > 0
  atMenu.value = lastWord.startsWith('@') && lastWord.length > 0
}

function applyCommand(cmd: { cmd: string; prompt: string }) {
  input.value = ''
  slashMenu.value = false
  const ctx = props.editorContext?.trim()
  const fullMsg = ctx ? `${cmd.prompt}\n\n${ctx}` : cmd.prompt
  doSend(fullMsg)
}

function applyFileRef(f: { name: string; content?: string }) {
  const name = f.name
  if (!files.value.some(x => x.name === name) && f.content) {
    files.value.push({ name, content: f.content })
  }
  // Remove @partial from input
  const pos = inputRef.value?.selectionStart ?? input.value.length
  const before = input.value.slice(0, pos).replace(/@\S*$/, '')
  const after = input.value.slice(pos)
  input.value = before + after
  atMenu.value = false
  nextTick(() => inputRef.value?.focus())
}

function dismissSuggestion() {
  slashMenu.value = false
  atMenu.value = false
}

function acceptSuggestion() {
  if (slashMenu.value && filteredCommands.value.length > 0) {
    applyCommand(filteredCommands.value[0])
  } else if (atMenu.value && filteredFiles.value.length > 0) {
    applyFileRef(filteredFiles.value[0])
  }
}

// ── Markdown renderer with code block actions ───────────────
let blockCounter = 0
const _blockEpoch = Date.now()

function esc(s: string) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function renderMd(text: string, msgId: string): string {
  if (!text) return ''
  blockCounter = 0
  let h = esc(text)

  // Code blocks with action buttons
  h = h.replace(/```(\w*)\n([\s\S]*?)```/g, (_match, lang: string, code: string) => {
    const id = `${_blockEpoch}-${msgId}-cb-${blockCounter++}`
    const displayLang = lang || 'text'
    return `<div class="ac-code-block" data-id="${id}">`
      + `<div class="ac-code-bar"><span class="ac-code-lang">${displayLang}</span>`
      + `<button class="ac-code-btn ac-code-copy">${t('aiPanel.copy')}</button>`
      + `<button class="ac-code-btn ac-code-insert">${t('aiPanel.insert')}</button>`
      + `</div>`
      + `<pre><code>${code}</code></pre></div>`
  })

  h = h.replace(/`([^`]+)`/g, '<code class="ac-inline-code">$1</code>')
  h = h.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  h = h.replace(/^### (.+)$/gm, '<h4>$1</h4>')
  h = h.replace(/^## (.+)$/gm, '<h3>$1</h3>')
  h = h.replace(/^# (.+)$/gm, '<h2>$1</h2>')
  h = h.replace(/^- (.+)$/gm, '<li>$1</li>')
  h = h.replace(/(<li>[\s\S]*?<\/li>)/g, '<ul>$1</ul>')
  h = h.replace(/\n/g, '<br/>')
  return DOMPurify.sanitize(h, { ADD_ATTR: ['data-id'] })
}

// ── File operations ─────────────────────────────────────────
async function attachFile() {
  try {
    const { open } = await import('@tauri-apps/plugin-dialog')
    const selected = await open({
      multiple: true,
      filters: [{ name: 'Text', extensions: ['md','txt','tex','py','js','ts','json','yaml','yml','xml','html','css','csv','pdf'] }]
    })
    if (!selected) return
    const paths = (Array.isArray(selected) ? selected : [selected]) as string[]
    for (const p of paths) {
      const name = p.split(/[\\/]/).pop() || p
      if (files.value.some(f => f.name === name)) continue
      try {
        const { readTextFile } = await import('@tauri-apps/plugin-fs')
        const content = await readTextFile(p)
        files.value.push({ name, content })
      } catch { /* skip unreadable files */ }
    }
  } catch { /* dialog not available */ }
}

function removeFile(name: string) {
  files.value = files.value.filter(f => f.name !== name)
}

// ── Send / Stream ───────────────────────────────────────────
async function send() {
  const text = input.value.trim()
  if (!text || streaming.value) return
  input.value = ''
  slashMenu.value = false
  atMenu.value = false

  // Build full message with file contents
  let fullMsg = text
  if (files.value.length) {
    const ctx = files.value.map(f => `--- File: ${f.name} ---\n${f.content.slice(0, 12000)}\n--- End ---`).join('\n\n')
    fullMsg = `${ctx}\n\n${text}`
    files.value = []
  }
  await doSend(fullMsg)
}

async function sendPreset(action: string) {
  if (streaming.value) return
  const ctx = props.editorContext?.trim()
  // 预设按钮是纯文本改写 —— 走一次性无工具的 /api/edit，
  // 绝不进 Agent ReAct 循环（否则 LLM 会尝试调 write_file 创建文档→死循环）。
  const instructions: Record<string, string> = {
    polish: '润色这段学术文本，改进语法、用词和流畅度，保持原意不变。只返回润色后的文本。',
    expand: '扩展这段学术文本，补充更多细节、论证和支撑。只返回扩展后的文本。',
    review: '审阅这段学术文本，逐条指出存在的问题并给出具体的改进建议。',
    en: '将以下内容翻译成流畅、地道的学术英文。只返回译文。',
    zh: '将以下内容翻译成流畅、地道的学术中文。只返回译文。',
  }
  const labels: Record<string, string> = {
    polish: t('aiPanel.presetPolishLabel'), expand: t('aiPanel.presetExpandLabel'), review: t('aiPanel.presetReviewLabel'),
    en: t('aiPanel.presetEnLabel'), zh: t('aiPanel.presetZhLabel'),
  }
  const instruction = instructions[action] || action
  if (!ctx) {
    messages.value.push({ id: crypto.randomUUID(), role: 'assistant', content: t('aiPanel.noText') })
    scrollBottom()
    return
  }
  await doEdit(instruction, ctx, labels[action] || action)
}

// 一次性文本改写：调用 /api/edit（无工具、不可能循环），流式写入聊天面板。
async function doEdit(instruction: string, text: string, label: string) {
  pendingApproval.value = null
  messages.value.push({ id: crypto.randomUUID(), role: 'user', content: label })
  scrollBottom()

  streaming.value = true
  streamContent.value = ''
  thinkingText.value = ''
  aiAbortCtrl.value = new AbortController()

  try {
    const resp = await fetch(`${API}/api/edit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, instruction }),
      signal: aiAbortCtrl.value.signal,
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: t('aiPanel.requestFailed') }))
      throw new Error(err.detail || `HTTP ${resp.status}`)
    }
    const reader = resp.body?.getReader()
    if (!reader) throw new Error(t('aiPanel.responseEmpty'))
    await readSseStream(reader, (evtType, d) => {
      if (evtType === 'delta' && d.content !== undefined) {
        // /api/edit 的 delta 携带累计全文
        streamContent.value = (d.content as string).replace(/<think\b[^>]*>[\s\S]*?<\/think\s*>/g, '').trim()
        scrollBottom()
      } else if (evtType === 'error') {
        streamContent.value = (d.message as string) || (d.content as string) || t('aiPanel.error')
      }
    })
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') return
    streamContent.value = t('aiPanel.errorPrefix', { msg: e instanceof Error ? e.message : String(e) })
  } finally {
    streaming.value = false; thinkingText.value = ''
    if (streamContent.value) {
      messages.value.push({ id: crypto.randomUUID(), role: 'assistant', content: streamContent.value })
    }
    streamContent.value = ''; aiAbortCtrl.value = null; scrollBottom()
  }
}

async function doSend(text: string) {
  pendingApproval.value = null
  acSessionId.value = null
  messages.value.push({ id: crypto.randomUUID(), role: 'user', content: text })
  scrollBottom()

  streaming.value = true
  streamContent.value = ''
  thinkingText.value = ''
  aiAbortCtrl.value = new AbortController()

  const history = messages.value
    .filter(m => !m.isStreaming).slice(-20)
    .map(m => ({ role: m.role, content: m.content }))

  try {
    const resp = await fetch(`${API}/api/agent/v2/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: text,
        history,
        context_text: props.editorContext?.trim() || undefined,
        context_file: props.activeFile?.trim() || undefined,
        workspace_root: rootDir.value?.trim() || undefined,
      }),
      signal: aiAbortCtrl.value.signal,
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: t('aiPanel.requestFailed') }))
      throw new Error(err.detail || `HTTP ${resp.status}`)
    }
    const reader = resp.body?.getReader()
    if (!reader) throw new Error(t('aiPanel.responseEmpty'))

    let hasToolActivity = false
    let _inThink = false
    let tokenBuffer = ''
    await readSseStream(reader, (evtType, d) => {
      const meta = d.metadata as Record<string, unknown> | undefined
      if (evtType === 'token' && d.content) {
        const c = d.content as string
        if (c.includes('</think')) _inThink = false
        if (!_inThink && !hasToolActivity) {
          const clean = c.replace(/<\/?think[^>]*>/g, '')
          if (clean) {
            tokenBuffer += clean
            streamContent.value = tokenBuffer
            scrollBottom()
          }
        }
        if (c.includes('<think') && !c.includes('</think')) _inThink = true
      }
      else if (evtType === 'response' && d.content) {
        streamContent.value = (d.content as string).replace(/<think\b[^>]*>[\s\S]*?<\/think\s*>/g, '').trim()
        tokenBuffer = ''
      }
      else if (evtType === 'error') { streamContent.value = (d.content as string) || t('aiPanel.error') }
      else if ((evtType === 'thought' || evtType === 'thinking') && d.content) { thinkingText.value = d.content as string }
      else if (evtType === 'tool_call') {
        hasToolActivity = true
        tokenBuffer = ''
        thinkingText.value = t('aiPanel.calling', { tool: ((meta?.tool_name as string) || (meta?.tool as string) || '...') })
      }
      else if (evtType === 'tool_result') { thinkingText.value = '' }
      else if (evtType === 'session_started') {
        acSessionId.value = (meta?.session_id as string) || acSessionId.value
      }
      else if (evtType === 'await_approval') {
        pendingApproval.value = {
          event_id: d.event_id as string || '',
          tool_name: (meta?.tool_name as string) || (meta?.tool as string) || '',
          args: (meta?.args ?? meta?.arguments) as Record<string, unknown> | undefined,
          risk: meta?.risk as string | undefined,
          reason: meta?.reason as string | undefined,
          preview: meta?.preview as Record<string, unknown> | undefined,
        }
      }
      else if (evtType === 'approval_received') { pendingApproval.value = null }
    })
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') return
    streamContent.value = t('aiPanel.errorPrefix', { msg: e instanceof Error ? e.message : String(e) })
  } finally {
    streaming.value = false; thinkingText.value = ''
    if (streamContent.value) {
      messages.value.push({ id: crypto.randomUUID(), role: 'assistant', content: streamContent.value })
    }
    streamContent.value = ''; aiAbortCtrl.value = null; scrollBottom()
  }
}

// Event delegation for code block Copy / Insert buttons
function handleCodeBlockClick(e: MouseEvent) {
  const btn = (e.target as HTMLElement).closest<HTMLElement>('.ac-code-btn')
  if (!btn) return
  const block = btn.closest<HTMLElement>('.ac-code-block')
  if (!block) return
  const code = block.querySelector('code')?.textContent ?? ''
  if (btn.classList.contains('ac-code-copy')) {
    navigator.clipboard.writeText(code).catch(() => {})
    btn.textContent = t('aiPanel.copied')
    setTimeout(() => { btn.textContent = t('aiPanel.copy') }, 1500)
  } else if (btn.classList.contains('ac-code-insert')) {
    emit('insert', code)
  }
}

function stopStream() {
  aiAbortCtrl.value?.abort()
}

async function handleApprovalDecision(decision: 'allow_once' | 'allow_session' | 'deny') {
  const sid = acSessionId.value
  const eventId = pendingApproval.value?.event_id
  if (!sid || !eventId) return
  pendingApproval.value = null
  try {
    await fetch(`${API}/api/agent/v2/approve/${sid}/${eventId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision }),
    })
  } catch { /* non-fatal */ }
}

function clearHistory() { messages.value = []; streamContent.value = '' }
function copyText(t: string, id?: string) {
  navigator.clipboard.writeText(t).catch(() => {})
  if (id) {
    copiedId.value = id
    if (copiedTimer) clearTimeout(copiedTimer)
    copiedTimer = setTimeout(() => { copiedId.value = null }, 1500)
  }
}
function scrollBottom() { nextTick(() => { if (messagesRef.value) messagesRef.value.scrollTop = messagesRef.value.scrollHeight }) }

watch(() => input.value, () => {
  nextTick(() => {
    if (inputRef.value) {
      inputRef.value.style.height = 'auto'
      inputRef.value.style.height = Math.min(inputRef.value.scrollHeight, 120) + 'px'
    }
  })
})
</script>

<style scoped>
.ai-chat-panel { display:flex; flex-direction:column; height:100%; background:var(--c-surface-2); border-left:1px solid var(--c-surface-3); font-size:var(--text-md); }

/* Header */
.ac-header { display:flex; align-items:center; justify-content:space-between; padding:var(--space-3); border-bottom:1px solid var(--c-surface-3); }
.ac-title-row { display:flex; align-items:center; gap:var(--space-2); color:var(--c-text-0); }
.ac-title { font-weight:600; font-size:var(--text-base); }
.ac-header-actions { display:flex; gap:var(--space-1); }
.ac-icon-btn { background:none; border:none; color:var(--c-text-2); cursor:pointer; padding:var(--space-1); border-radius:var(--radius-xs); display:flex; }
.ac-icon-btn:not(:disabled):hover { background:var(--c-surface-4); color:var(--c-text-0); }
.ac-icon-btn:focus-visible { outline:none; box-shadow:var(--ring-focus); color:var(--c-text-0); }
.ac-icon-btn:disabled { opacity:.3; cursor:not-allowed; }

/* Context */
.ac-context { display:flex; align-items:center; gap:var(--space-2); padding:var(--space-2) var(--space-3); font-size:var(--text-xs); color:var(--c-accent); background:var(--c-accent-soft); border-bottom:1px solid var(--c-surface-3); }
.ac-context svg { flex-shrink:0; }

/* Messages */
.ac-messages { flex:1; overflow-y:auto; padding:var(--space-3); display:flex; flex-direction:column; gap:var(--space-3); }
.ac-empty { text-align:center; padding:var(--space-7) var(--space-5); color:var(--c-text-2); }
.ac-empty-icon { margin-bottom:var(--space-3); color:var(--c-accent); opacity:.55; animation: ac-float 3.6s var(--ease-smooth) infinite; }
@keyframes ac-float { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-4px); } }
@media (prefers-reduced-motion: reduce) { .ac-empty-icon { animation: none; } }
.ac-empty p { margin:var(--space-1) 0; font-size:var(--text-base); }
.ac-empty-title { color:var(--c-text-1); }
.ac-empty-sub { font-size:var(--text-sm)!important; color:var(--c-text-2); animation-delay:.08s; }
.ac-empty code { background:var(--c-surface-3); color:var(--c-accent-hover); padding:var(--space-0) var(--space-2); border-radius:var(--radius-xs); font-size:var(--text-sm); font-family:var(--font-mono); }

/* Message bubble */
.ac-msg { display:flex; gap:var(--space-2); max-width:100%; animation: ac-msg-in var(--motion-slow) var(--ease-out) both; }
@keyframes ac-msg-in {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0); }
}
@media (prefers-reduced-motion: reduce) { .ac-msg { animation: none; } }
.ac-msg.user { flex-direction:row-reverse; }
.ac-avatar { width:28px; height:28px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:var(--text-xs); font-weight:700; flex-shrink:0; }
.ac-msg.user .ac-avatar { background:var(--c-accent); color:#fff; }
.ac-msg.assistant .ac-avatar { background:var(--c-surface-4); color:var(--c-text-0); border:1px solid var(--c-surface-3); }

.ac-body { min-width:0; max-width:88%; }
.ac-msg.user .ac-body { text-align:right; }

.ac-user-bubble { display:inline-block; text-align:left; background:var(--c-accent); color:#fff; padding:var(--space-2) var(--space-3); border-radius:var(--radius-lg) var(--radius-lg) var(--radius-xs) var(--radius-lg); font-size:var(--text-md); line-height:var(--leading-snug); word-break:break-word; white-space:pre-wrap; }

.ac-thinking { font-size:var(--text-sm); color:var(--c-accent); margin-bottom:var(--space-1); padding:var(--space-1) var(--space-2); border-left:2px solid var(--c-accent); background:var(--c-accent-soft); border-radius:0 var(--radius-xs) var(--radius-xs) 0; }

.ac-ai-bubble { background:var(--c-surface-3); border:1px solid var(--c-surface-4); padding:var(--space-2) var(--space-3); border-radius:var(--radius-lg); font-size:var(--text-md); line-height:var(--leading-relaxed); word-break:break-word; color:var(--c-text-0); }
.ac-ai-bubble :is(h2,h3,h4) { margin:var(--space-2) 0 var(--space-1); color:var(--c-text-0); }
.ac-waiting { color:var(--c-text-2); font-style:italic; }

/* Code blocks with action bar — :deep() needed because blocks are rendered via v-html */
:deep(.ac-code-block) { margin:var(--space-2) 0; border-radius:var(--radius-sm); overflow:hidden; border:1px solid var(--c-surface-4); }
:deep(.ac-code-bar) { display:flex; justify-content:space-between; align-items:center; padding:var(--space-1) var(--space-3); background:var(--c-surface-4); font-size:var(--text-xs); }
:deep(.ac-code-lang) { color:var(--c-text-2); font-family:var(--font-mono); }
:deep(.ac-code-btn) { background:none; border:none; color:var(--c-accent); cursor:pointer; font-size:var(--text-xs); padding:var(--space-0) var(--space-2); border-radius:var(--radius-xs); transition:background var(--motion-fast) var(--ease-out), transform var(--motion-fast) var(--ease-brush); }
:deep(.ac-code-btn):hover { background:var(--c-accent-soft); }
:deep(.ac-code-btn):active { transform:scale(0.94); }
:deep(.ac-code-block pre) { background:var(--c-surface-2); color:var(--c-text-0); padding:var(--space-3); margin:0; overflow-x:auto; font-size:var(--text-sm); line-height:var(--leading-normal); font-family:var(--font-mono); }
:deep(.ac-code-block code) { background:none; padding:0; font-size:var(--text-sm); color:inherit; }
:deep(.ac-inline-code) { background:var(--c-surface-3); padding:1px 5px; border-radius:var(--radius-xs); font-size:var(--text-sm); color:var(--c-text-1); font-family:var(--font-mono); }

.ac-cursor { display:inline-block; width:2px; height:16px; background:var(--c-accent); margin-left:2px; margin-top:var(--space-1); animation:ac-blink 1s step-end infinite; vertical-align:text-bottom; }
@keyframes ac-blink { 50% { opacity:0; } }

.ac-actions { display:flex; gap:var(--space-2); margin-top:var(--space-2); }
.ac-action-btn { background:none; border:1px solid var(--c-surface-4); color:var(--c-text-2); padding:var(--space-1) var(--space-2); border-radius:var(--radius-xs); font-size:var(--text-xs); cursor:pointer; display:flex; align-items:center; gap:var(--space-1); }
.ac-action-btn:not(:disabled):hover { background:var(--c-surface-3); color:var(--c-text-0); border-color:var(--c-accent); }
.ac-action-btn:focus-visible { outline:none; box-shadow:var(--ring-focus); border-color:var(--c-accent); }
.ac-action-btn.copied { color:var(--c-success); border-color:var(--c-success-border); background:var(--c-success-bg); }

/* File attachments */
.ac-attachments { display:flex; gap:var(--space-2); flex-wrap:wrap; padding:var(--space-2) var(--space-3); border-top:1px solid var(--c-surface-3); }
.ac-file { display:flex; align-items:center; gap:var(--space-1); background:var(--c-surface-3); border:1px solid var(--c-surface-4); border-radius:var(--radius-xs); padding:var(--space-1) var(--space-2); font-size:var(--text-xs); color:var(--c-text-1); }
.ac-file:hover { border-color:var(--c-accent); }
.ac-file svg { flex-shrink:0; color:var(--c-text-2); }
.ac-file-x { background:none; border:none; color:var(--c-text-2); cursor:pointer; font-size:var(--text-base); line-height:1; padding:0 var(--space-0); border-radius:var(--radius-xs); transition:color var(--motion-fast) var(--ease-out), background var(--motion-fast) var(--ease-out); }
.ac-file-x:hover { color:var(--c-danger); background:var(--c-danger-bg); }

/* Presets */
.ac-presets { display:flex; gap:var(--space-2); flex-wrap:wrap; padding:var(--space-2) var(--space-3); border-top:1px solid var(--c-surface-3); }
.ac-preset { background:var(--c-surface-3); border:1px solid var(--c-surface-4); border-radius:var(--radius-pill); padding:var(--space-1) var(--space-3); color:var(--c-text-1); font-size:var(--text-sm); cursor:pointer; }
.ac-preset:not(:disabled):hover { border-color:var(--c-accent); color:var(--c-text-0); background:var(--c-accent-soft); }
.ac-preset:focus-visible { outline:none; box-shadow:var(--ring-focus); border-color:var(--c-accent); }

/* Input */
.ac-input-area { display:flex; align-items:flex-end; gap:var(--space-2); padding:var(--space-3); border-top:1px solid var(--c-surface-3); }
.ac-attach-btn { width:34px; height:34px; border-radius:var(--radius-sm); background:none; border:1px solid var(--c-surface-4); color:var(--c-text-2); cursor:pointer; display:flex; align-items:center; justify-content:center; flex-shrink:0; }
.ac-attach-btn:not(:disabled):hover { background:var(--c-surface-3); color:var(--c-text-0); border-color:var(--c-accent); }
.ac-attach-btn:focus-visible { outline:none; box-shadow:var(--ring-focus); border-color:var(--c-accent); }
.ac-attach-btn:disabled { opacity:.4; cursor:not-allowed; }
.ac-attach-btn.voice-active { background:var(--c-accent); color:#fff; border-color:var(--c-accent); animation:voice-pulse 1.5s ease-in-out infinite; }

.ac-input-wrap { flex:1; position:relative; }
.ac-input { width:100%; background:var(--c-surface-3); border:1px solid var(--c-surface-4); border-radius:var(--radius-sm); padding:var(--space-2) var(--space-3); color:var(--c-text-0); font-size:var(--text-md); font-family:inherit; line-height:var(--leading-snug); resize:none; outline:none; max-height:120px; box-sizing:border-box; transition:border-color var(--motion-base) var(--ease-out), box-shadow var(--motion-base) var(--ease-out); }
.ac-input:focus { border-color:var(--c-accent); box-shadow:var(--ring-focus); }
.ac-input::placeholder { color:var(--c-text-3); }
.ac-input:disabled { opacity:.5; }

/* Dropdown menus */
.ac-menu { position:absolute; bottom:100%; left:0; right:0; transform-origin:bottom center; background:var(--c-surface-3); border:1px solid var(--c-surface-4); border-radius:var(--radius-sm); max-height:240px; overflow-y:auto; margin-bottom:var(--space-1); box-shadow:var(--elevation-3); z-index:10; }
.ac-menu-item { display:flex; align-items:center; gap:var(--space-3); padding:var(--space-2) var(--space-3); cursor:pointer; font-size:var(--text-sm); color:var(--c-text-0); transition:background var(--motion-fast) var(--ease-out); }
.ac-menu-item:hover { background:var(--c-accent-soft); }
.ac-menu-item svg { flex-shrink:0; color:var(--c-text-2); }
.ac-menu-cmd { font-weight:600; color:var(--c-accent); min-width:80px; font-family:var(--font-mono); }
.ac-menu-desc { color:var(--c-text-2); }

.ac-send-btn { width:34px; height:34px; border-radius:var(--radius-sm); background:var(--c-accent); border:none; color:#fff; cursor:pointer; display:flex; align-items:center; justify-content:center; flex-shrink:0; }
.ac-send-btn:not(:disabled):hover { background:var(--c-accent-hover); }
.ac-send-btn:focus-visible { outline:none; box-shadow:var(--ring-focus); }
.ac-send-btn:disabled { opacity:.4; cursor:not-allowed; }
.ac-send-btn.stopping { background: var(--c-danger); animation: stop-ring 1.8s ease-in-out infinite; }
@keyframes stop-ring {
  0%, 100% { box-shadow: 0 0 0 0 var(--c-danger-border); }
  50%       { box-shadow: 0 0 0 5px transparent; }
}
@media (prefers-reduced-motion: reduce) { .ac-send-btn.stopping { animation: none; } }

/* Thinking scan bar */
.ac-thinking-bar {
  height: 2px;
  flex-shrink: 0;
  background: linear-gradient(90deg, transparent 0%, var(--c-accent) 45%, transparent 100%);
  background-size: 40% 100%;
  background-repeat: no-repeat;
  animation: ac-scan 1.4s ease-in-out infinite;
}
@keyframes ac-scan {
  0%   { background-position: -40% 0; }
  100% { background-position: 140% 0; }
}
@media (prefers-reduced-motion: reduce) { .ac-thinking-bar { animation: none; background-position: 50% 0; } }

/* Wave dots (used in waiting state) */
.dot-wave { display: inline-flex; gap: var(--space-1); align-items: center; padding: var(--space-0) 0; }
.dot-wave i {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--c-accent); display: block;
  animation: ac-wave 1.1s ease-in-out infinite;
}
.dot-wave i:nth-child(2) { animation-delay: 0.18s; }
.dot-wave i:nth-child(3) { animation-delay: 0.36s; }
@keyframes ac-wave {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.3; }
  30%            { transform: translateY(-5px); opacity: 1; }
}
@media (prefers-reduced-motion: reduce) { .dot-wave i { animation: none; opacity: .7; } }
</style>
