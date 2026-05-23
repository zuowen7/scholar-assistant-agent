<template>
  <div class="ai-chat-panel">
    <!-- Header -->
    <div class="ac-header">
      <div class="ac-title-row">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
        <span class="ac-title">AI 对话</span>
      </div>
      <div class="ac-header-actions">
        <button class="ac-icon-btn" @click="clearHistory" title="清空" :disabled="messages.length===0||streaming">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 102.13-9.36L1 10"/></svg>
        </button>
        <button class="ac-icon-btn" @click="$emit('undo')" title="撤销插入" :disabled="!canUndo">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7v6h6"/><path d="M21 17a9 9 0 00-15-6.7L3 13"/></svg>
        </button>
        <button class="ac-icon-btn" @click="$emit('close')" title="关闭">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
        </button>
      </div>
    </div>

    <!-- Context bar -->
    <div class="ac-context" v-if="editorContext">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
      <span>已带入编辑器上下文：{{ editorContext.length }} 字符</span>
    </div>

    <!-- Thinking scan bar -->
    <div v-if="streaming" class="ac-thinking-bar"></div>

    <!-- Messages -->
    <div class="ac-messages" ref="messagesRef" @click="handleCodeBlockClick">
      <div v-if="messages.length===0 && !streaming" class="ac-empty">
        <div class="ac-empty-icon">
          <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2"><circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/></svg>
        </div>
        <p>你好，我是你的学术写作助手。</p>
        <p class="ac-empty-sub">输入 <code>/</code> 使用命令，输入 <code>@</code> 引用文件。</p>
      </div>

      <div v-for="msg in messages" :key="msg.id" class="ac-msg" :class="msg.role">
        <div class="ac-avatar">{{ msg.role==='user'?'U':'AI' }}</div>
        <div class="ac-body">
          <div v-if="msg.role==='user'" class="ac-user-bubble">{{ msg.content }}</div>
          <template v-else>
            <div v-if="msg.thinking" class="ac-thinking">{{ msg.thinking }}</div>
            <div class="ac-ai-bubble" v-html="renderMd(msg.content, msg.id)"></div>
            <div v-if="msg.isStreaming" class="ac-cursor"></div>
            <div v-if="!msg.isStreaming && msg.content" class="ac-actions">
              <button class="ac-action-btn" @click="$emit('insert', msg.content)">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
                插入
              </button>
              <button class="ac-action-btn" @click="copyText(msg.content)">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
                复制
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
      <div class="ac-file" v-for="f in files" :key="f.name">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
        <span>{{ f.name }}</span>
        <button class="ac-file-x" title="移除附件" @click="removeFile(f.name)">×</button>
      </div>
    </div>

    <!-- Presets -->
    <div class="ac-presets" v-if="!streaming">
      <button class="ac-preset" @click="sendPreset('polish')">润色</button>
      <button class="ac-preset" @click="sendPreset('expand')">扩写</button>
      <button class="ac-preset" @click="sendPreset('review')">审查</button>
      <button class="ac-preset" @click="sendPreset('en')">英译</button>
      <button class="ac-preset" @click="sendPreset('zh')">中译</button>
    </div>

    <!-- Input area -->
    <div class="ac-input-area">
      <button class="ac-attach-btn" @click="attachFile" title="添加附件" :disabled="streaming">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"/></svg>
      </button>
      <div class="ac-input-wrap">
        <textarea
          ref="inputRef"
          v-model="input"
          class="ac-input"
          placeholder="输入问题...（/ 命令，@ 引用文件）"
          @keydown.enter.exact.prevent="send"
          @keydown.tab.exact.prevent="acceptSuggestion"
          @keydown.escape="dismissSuggestion"
          @input="onInput"
          :disabled="streaming"
          rows="1"
        />
        <!-- Slash command menu -->
        <div v-if="slashMenu" class="ac-menu ac-slash-menu">
          <div v-for="cmd in filteredCommands" :key="cmd.cmd" class="ac-menu-item" @click="applyCommand(cmd)">
            <span class="ac-menu-cmd">{{ cmd.cmd }}</span>
            <span class="ac-menu-desc">{{ cmd.desc }}</span>
          </div>
        </div>
        <!-- @ reference menu -->
        <div v-if="atMenu" class="ac-menu ac-at-menu">
          <div v-for="f in filteredFiles" :key="f.name" class="ac-menu-item" @click="applyFileRef(f)">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
            <span>{{ f.name }}</span>
          </div>
        </div>
      </div>
      <button
        class="ac-send-btn"
        :class="{ stopping: streaming }"
        @click="streaming ? stopStream() : send()"
        :disabled="!streaming && !input.trim()"
        :title="streaming ? '停止生成' : '发送'"
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
import DOMPurify from 'dompurify'
import { readSseStream } from '../utils/streamReader'
import { aiMessages, aiStreaming, aiStreamContent, aiThinkingText, aiAbortCtrl } from '../composables/useAiPanelState'
import type { AiPanelMsg } from '../composables/useAiPanelState'
import { API_BASE } from '../utils/api'
import AgentApprovalInline from './AgentApprovalInline.vue'
import type { PendingApproval } from '../composables/useAgentChat'
import { useFileTree } from '../composables/useFileTree'

const props = defineProps<{
  editorContext: string
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
const acSessionId = ref<string | null>(null)
const pendingApproval = ref<PendingApproval | null>(null)
const { rootDir } = useFileTree()

// ── Slash commands ──────────────────────────────────────────
const commands = [
  { cmd: '/explain', prompt: 'Please explain the following text in detail, breaking down the key concepts:', desc: '解释文本' },
  { cmd: '/fix', prompt: 'Please identify and fix any issues in the following text:', desc: '修复问题' },
  { cmd: '/translate', prompt: 'Please translate the following text:', desc: '翻译文本' },
  { cmd: '/polish', prompt: 'Please polish the following academic text, improving grammar, vocabulary and style:', desc: '润色写作' },
  { cmd: '/expand', prompt: 'Please expand the following text with more details and academic depth:', desc: '扩写内容' },
  { cmd: '/summarize', prompt: 'Please provide a concise summary of the following text:', desc: '总结内容' },
  { cmd: '/outline', prompt: 'Please generate a detailed outline for a paper on the following topic:', desc: '生成提纲' },
  { cmd: '/review', prompt: 'Please review the following academic text, identify issues and suggest improvements:', desc: '审查文本' },
  { cmd: '/rewrite', prompt: 'Please rewrite the following text to improve clarity and flow:', desc: '改写文本' },
  { cmd: '/cite', prompt: 'Please generate proper academic citations (IEEE/APA/GB-T) for the following references:', desc: '格式化引用' },
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
      + `<button class="ac-code-btn ac-code-copy">复制</button>`
      + `<button class="ac-code-btn ac-code-insert">插入</button>`
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
  const prompts: Record<string, string> = {
    polish: 'Please polish the following academic text:',
    expand: 'Please expand the following text with more details:',
    review: 'Please review the following academic text:',
    en: 'Please translate into fluent academic English:',
    zh: 'Please translate into fluent academic Chinese:',
  }
  const fullMsg = ctx ? `${prompts[action] || action}\n\n${ctx}` : (prompts[action] || action)
  await doSend(fullMsg)
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
        workspace_root: rootDir.value?.trim() || undefined,
      }),
      signal: aiAbortCtrl.value.signal,
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: '请求失败' }))
      throw new Error(err.detail || `HTTP ${resp.status}`)
    }
    const reader = resp.body?.getReader()
    if (!reader) throw new Error('响应内容为空')

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
      else if (evtType === 'error') { streamContent.value = (d.content as string) || '错误' }
      else if ((evtType === 'thought' || evtType === 'thinking') && d.content) { thinkingText.value = d.content as string }
      else if (evtType === 'tool_call') {
        hasToolActivity = true
        tokenBuffer = ''
        thinkingText.value = '正在调用：' + ((meta?.tool_name as string) || (meta?.tool as string) || '...')
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
    streamContent.value = `错误：${e instanceof Error ? e.message : String(e)}`
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
    btn.textContent = '已复制'
    setTimeout(() => { btn.textContent = '复制' }, 1500)
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
function copyText(t: string) { navigator.clipboard.writeText(t).catch(() => {}) }
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
.ai-chat-panel { display:flex; flex-direction:column; height:100%; background:var(--panel-bg,#1e1e1e); border-left:1px solid var(--border-color,#333); font-size:13px; }

/* Header */
.ac-header { display:flex; align-items:center; justify-content:space-between; padding:10px 12px; border-bottom:1px solid var(--border-color,#333); }
.ac-title-row { display:flex; align-items:center; gap:8px; color:var(--text-primary,#e0e0e0); }
.ac-title { font-weight:600; font-size:14px; }
.ac-header-actions { display:flex; gap:4px; }
.ac-icon-btn { background:none; border:none; color:var(--text-secondary,#888); cursor:pointer; padding:4px; border-radius:4px; display:flex; }
.ac-icon-btn:hover { background:var(--hover-bg,#2d2d2d); color:var(--text-primary,#e0e0e0); }
.ac-icon-btn:disabled { opacity:.3; cursor:not-allowed; }

/* Context */
.ac-context { display:flex; align-items:center; gap:6px; padding:6px 12px; font-size:11px; color:var(--accent,#7c6ef0); background:var(--accent-bg,rgba(124,110,240,.1)); border-bottom:1px solid var(--border-color,#333); }

/* Messages */
.ac-messages { flex:1; overflow-y:auto; padding:12px; display:flex; flex-direction:column; gap:12px; }
.ac-empty { text-align:center; padding:40px 20px; color:var(--text-secondary,#888); }
.ac-empty-icon { margin-bottom:12px; opacity:.4; }
.ac-empty p { margin:4px 0; font-size:14px; }
.ac-empty-sub { font-size:12px!important; opacity:.7; }
.ac-empty code { background:rgba(255,255,255,.08); padding:2px 6px; border-radius:3px; font-size:12px; }

/* Message bubble */
.ac-msg { display:flex; gap:10px; max-width:100%; }
.ac-msg.user { flex-direction:row-reverse; }
.ac-avatar { width:28px; height:28px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:11px; font-weight:700; flex-shrink:0; }
.ac-msg.user .ac-avatar { background:var(--accent,#7c6ef0); color:#fff; }
.ac-msg.assistant .ac-avatar { background:var(--hover-bg,#2d2d2d); color:var(--text-primary,#e0e0e0); border:1px solid var(--border-color,#333); }

.ac-body { min-width:0; max-width:88%; }
.ac-msg.user .ac-body { text-align:right; }

.ac-user-bubble { display:inline-block; text-align:left; background:var(--accent,#7c6ef0); color:#fff; padding:8px 12px; border-radius:12px 12px 4px 12px; font-size:13px; line-height:1.5; word-break:break-word; white-space:pre-wrap; }

.ac-thinking { font-size:12px; color:var(--accent,#7c6ef0); opacity:.8; margin-bottom:4px; padding:4px 8px; border-left:2px solid var(--accent,#7c6ef0); }

.ac-ai-bubble { background:var(--code-bg,#1a1a2e); border:1px solid var(--border-color,#333); padding:10px 12px; border-radius:12px; font-size:13px; line-height:1.6; word-break:break-word; color:var(--text-primary,#e0e0e0); }
.ac-ai-bubble :is(h2,h3,h4) { margin:8px 0 4px; }
.ac-waiting { color:var(--text-secondary,#888); font-style:italic; }

/* Code blocks with action bar — :deep() needed because blocks are rendered via v-html */
:deep(.ac-code-block) { margin:8px 0; border-radius:6px; overflow:hidden; border:1px solid var(--border-color,#333); }
:deep(.ac-code-bar) { display:flex; justify-content:space-between; align-items:center; padding:4px 10px; background:var(--hover-bg,#2d2d2d); font-size:11px; }
:deep(.ac-code-lang) { color:var(--text-secondary,#888); }
:deep(.ac-code-btn) { background:none; border:none; color:var(--accent,#7c6ef0); cursor:pointer; font-size:11px; padding:2px 8px; border-radius:3px; }
:deep(.ac-code-btn):hover { background:var(--accent-bg,rgba(124,110,240,.15)); }
:deep(.ac-code-block pre) { background:var(--code-bg,#1a1a2e); color:var(--text-primary,#e0e0e0); padding:10px; margin:0; overflow-x:auto; font-size:12px; line-height:1.5; }
:deep(.ac-code-block code) { background:none; padding:0; font-size:12px; color:inherit; }
:deep(.ac-inline-code) { background:var(--c-surface-3); padding:1px 5px; border-radius:3px; font-size:12px; color:var(--c-text-1); }

.ac-cursor { display:inline-block; width:2px; height:16px; background:var(--accent,#7c6ef0); margin-left:2px; margin-top:4px; animation:blink 1s step-end infinite; vertical-align:text-bottom; }
@keyframes blink { 50% { opacity:0; } }

.ac-actions { display:flex; gap:6px; margin-top:6px; }
.ac-action-btn { background:none; border:1px solid var(--border-color,#333); color:var(--text-secondary,#888); padding:3px 8px; border-radius:4px; font-size:11px; cursor:pointer; display:flex; align-items:center; gap:4px; }
.ac-action-btn:hover { background:var(--hover-bg,#2d2d2d); color:var(--text-primary,#e0e0e0); border-color:var(--accent,#7c6ef0); }

/* File attachments */
.ac-attachments { display:flex; gap:6px; flex-wrap:wrap; padding:6px 12px; border-top:1px solid var(--border-color,#333); }
.ac-file { display:flex; align-items:center; gap:4px; background:var(--code-bg,#1a1a2e); border:1px solid var(--border-color,#333); border-radius:4px; padding:3px 8px; font-size:11px; color:var(--text-secondary,#888); }
.ac-file-x { background:none; border:none; color:var(--text-secondary,#888); cursor:pointer; font-size:14px; line-height:1; padding:0 2px; }
.ac-file-x:hover { color:var(--text-primary,#e0e0e0); }

/* Presets */
.ac-presets { display:flex; gap:6px; flex-wrap:wrap; padding:8px 12px; border-top:1px solid var(--border-color,#333); }
.ac-preset { background:var(--hover-bg,#2d2d2d); border:1px solid var(--border-color,#333); border-radius:14px; padding:4px 12px; color:var(--text-secondary,#888); font-size:12px; cursor:pointer; transition:all .15s; }
.ac-preset:hover { border-color:var(--accent,#7c6ef0); color:var(--text-primary,#e0e0e0); }

/* Input */
.ac-input-area { display:flex; align-items:flex-end; gap:6px; padding:10px 12px; border-top:1px solid var(--border-color,#333); }
.ac-attach-btn { width:34px; height:34px; border-radius:8px; background:none; border:1px solid var(--border-color,#333); color:var(--text-secondary,#888); cursor:pointer; display:flex; align-items:center; justify-content:center; flex-shrink:0; }
.ac-attach-btn:hover { background:var(--hover-bg,#2d2d2d); color:var(--text-primary,#e0e0e0); }
.ac-attach-btn:disabled { opacity:.4; cursor:not-allowed; }

.ac-input-wrap { flex:1; position:relative; }
.ac-input { width:100%; background:var(--input-bg,#2d2d2d); border:1px solid var(--border-color,#333); border-radius:8px; padding:8px 12px; color:var(--text-primary,#e0e0e0); font-size:13px; font-family:inherit; line-height:1.4; resize:none; outline:none; max-height:120px; box-sizing:border-box; }
.ac-input:focus { border-color:var(--accent,#7c6ef0); }
.ac-input::placeholder { color:var(--text-secondary,#888); }
.ac-input:disabled { opacity:.5; }

/* Dropdown menus */
.ac-menu { position:absolute; bottom:100%; left:0; right:0; background:var(--surface,#252535); border:1px solid var(--border-color,#333); border-radius:8px; max-height:240px; overflow-y:auto; margin-bottom:4px; box-shadow:0 -8px 24px rgba(0,0,0,.3); z-index:10; }
.ac-menu-item { display:flex; align-items:center; gap:10px; padding:8px 12px; cursor:pointer; font-size:12px; color:var(--text-primary,#e0e0e0); }
.ac-menu-item:hover { background:var(--hover-bg,#2d2d2d); }
.ac-menu-cmd { font-weight:600; color:var(--accent,#7c6ef0); min-width:80px; }
.ac-menu-desc { color:var(--text-secondary,#888); }

.ac-send-btn { width:34px; height:34px; border-radius:8px; background:var(--accent,#7c6ef0); border:none; color:#fff; cursor:pointer; display:flex; align-items:center; justify-content:center; flex-shrink:0; transition: background 0.15s; }
.ac-send-btn:hover { opacity:.9; }
.ac-send-btn:disabled { opacity:.4; cursor:not-allowed; }
.ac-send-btn.stopping { background: var(--c-danger, #ef4444); animation: stop-ring 1.8s ease-in-out infinite; }
@keyframes stop-ring {
  0%, 100% { box-shadow: 0 0 0 0 rgba(239,68,68,0.4); }
  50%       { box-shadow: 0 0 0 5px rgba(239,68,68,0); }
}

/* Thinking scan bar */
.ac-thinking-bar {
  height: 2px;
  flex-shrink: 0;
  background: linear-gradient(90deg, transparent 0%, var(--accent,#7c6ef0) 45%, transparent 100%);
  background-size: 40% 100%;
  background-repeat: no-repeat;
  animation: ac-scan 1.4s ease-in-out infinite;
}
@keyframes ac-scan {
  0%   { background-position: -40% 0; }
  100% { background-position: 140% 0; }
}

/* Wave dots (used in waiting state) */
.dot-wave { display: inline-flex; gap: 4px; align-items: center; padding: 2px 0; }
.dot-wave i {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--accent,#7c6ef0); display: block;
  animation: ac-wave 1.1s ease-in-out infinite;
}
.dot-wave i:nth-child(2) { animation-delay: 0.18s; }
.dot-wave i:nth-child(3) { animation-delay: 0.36s; }
@keyframes ac-wave {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.3; }
  30%            { transform: translateY(-5px); opacity: 1; }
}

/* ── Light mode ── */
:global([data-theme="light"]) :deep(.ac-code-block pre) { background: var(--c-surface-0); color: var(--c-text-0); }
:global([data-theme="light"]) :deep(.ac-inline-code) { background: var(--c-surface-3); }
:global([data-theme="light"]) .ac-empty code { background: var(--c-surface-3); }
:global([data-theme="light"]) .ac-menu { background: var(--c-surface-1); box-shadow: var(--elevation-3); }
</style>
