<template>
  <div
    class="agent-panel"
    :class="{ open, standalone: isStandalone }"
  >
    <div
      class="agent-header"
      :class="{ 'window-drag': isStandalone }"
      @mousedown="onHeaderMouseDown"
    >
      <div class="agent-tabs">
        <button class="agent-tab" :class="{ active: tab === 'chat' }" @click="tab = 'chat'">对话</button>
        <button class="agent-tab" :class="{ active: tab === 'docs' }" @click="tab = 'docs'">知识库</button>
        <button class="agent-tab" :class="{ active: tab === 'templates' }" @click="tab = 'templates'">模板</button>
        <button class="agent-tab" :class="{ active: tab === 'sessions' }" @click="tab = 'sessions'; refreshSessions()">会话</button>
      </div>
      <div class="agent-header-actions">
        <!-- Standalone: dock back button -->
        <button v-if="isStandalone" class="agent-hdr-btn" title="停靠回主窗口" @click="onDockBack">
          <PinOff :size="13" :stroke-width="1.8" />
        </button>
        <!-- Main window: float out button -->
        <button v-if="!isStandalone" class="agent-hdr-btn" :title="_agentWindow ? '停靠' : '弹出独立窗口'" @click="toggleFloat">
          <PinOff v-if="_agentWindow" :size="13" :stroke-width="1.8" />
          <Pin v-else :size="13" :stroke-width="1.8" />
        </button>
        <button v-if="!isStandalone" class="agent-close-btn" @click="$emit('update:open', false)" aria-label="关闭">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>
    </div>

    <!-- Sessions Tab -->
    <div v-show="tab === 'sessions'" class="agent-sessions">
      <AgentSessionList ref="sessionListRef" @resume="handleSessionResume" />
    </div>

    <!-- Chat Tab -->
    <div v-show="tab === 'chat'" class="agent-chat">
      <div class="agent-messages" ref="messagesRef">
        <div v-if="currentStatus && sending && !pendingApproval" class="agent-status-bar">
          <span class="dot-pulse"></span>
          <span class="agent-status-text">{{ currentStatus }}</span>
        </div>
        <AgentApprovalInline
          v-if="sending"
          :pending="pendingApproval"
          @decide="handleApprovalDecision"
        />
        <div v-if="messages.length === 0 && !sending" class="agent-empty">
          <p>Ask anything. The ink is ready.</p>
          <p class="hint">支持搜索文档、翻译文本、查询 arXiv 论文</p>
        </div>
        <div v-for="msg in messages" :key="msg.id" class="agent-msg" :class="msg.role">
          <template v-for="(evt, i) in msg.events" :key="i">
            <div v-if="evt.type === 'task_started'" class="agent-event task-lifecycle">
              <span class="evt-lifecycle-icon">&#x25B6;</span>
              <span class="evt-label">任务</span>
              <span class="evt-task-title">{{ evt.metadata?.title || evt.content }}</span>
              <span v-if="evt.metadata?.index != null" class="evt-task-progress">{{ evt.metadata.index }}/{{ evt.metadata.total }}</span>
            </div>
            <div v-else-if="evt.type === 'task_done'" class="agent-event task-lifecycle done">
              <span class="evt-lifecycle-icon">&#x2714;</span>
              <span class="evt-label">任务完成</span>
              <span class="evt-task-id">{{ evt.metadata?.task_id }}</span>
            </div>
            <div v-else-if="evt.type === 'thought' || evt.type === 'thinking'" class="agent-event thinking">
              <span class="evt-thinking-dot"></span>
              <span class="evt-label">{{ evt.type === 'thought' ? '思考' : '推理' }}</span>
              <span class="evt-content-text">{{ evt.content }}</span>
            </div>
            <div v-else-if="evt.type === 'tool_call'" class="agent-event tool-call">
              <div class="evt-tool-header">
                <span class="evt-tool-icon">&#x26A1;</span>
                <span class="evt-label">调用工具</span>
                <span class="evt-tool-name">{{ evt.metadata?.tool_name || evt.metadata?.tool || evt.content }}</span>
                <span v-if="evt.metadata?.risk" class="evt-risk-badge" :class="'risk-' + evt.metadata.risk">{{ evt.metadata.risk }}</span>
              </div>
              <div class="evt-tool-desc">{{ getToolDescription(evt.metadata?.tool_name || evt.metadata?.tool) }}</div>
              <div v-if="(evt.metadata?.arguments || evt.metadata?.args) && Object.keys((evt.metadata?.arguments || evt.metadata?.args) as any).length" class="evt-tool-args">
                <span class="evt-args-label">参数</span>
                <code class="evt-args-code">{{ formatToolArgs((evt.metadata?.arguments || evt.metadata?.args) as any) }}</code>
              </div>
            </div>
            <div v-else-if="evt.type === 'tool_result'" class="agent-event tool-result" :class="{ 'evt-error': evt.metadata?.error }">
              <div class="evt-result-header">
                <span v-if="evt.metadata?.error" class="evt-tool-icon error">&#x2717;</span>
                <span v-else class="evt-tool-icon success">&#x2713;</span>
                <span class="evt-label">{{ evt.metadata?.error ? '执行失败' : '执行完成' }}</span>
                <span class="evt-result-tool">{{ evt.metadata?.tool_name || evt.metadata?.tool }}</span>
                <span v-if="evt.metadata?.duration_ms" class="evt-duration">{{ evt.metadata.duration_ms }}ms</span>
              </div>
              <div class="evt-result-preview">{{ truncateResult(evt.content) }}</div>
            </div>
            <div v-else-if="evt.type === 'warning'" class="agent-event warning">
              <span class="evt-warning-icon">&#x26A0;</span>
              <span class="evt-content-text">{{ evt.content }}</span>
            </div>
          </template>
          <div v-if="msg.content" class="agent-bubble">{{ msg.content }}</div>
          <div v-if="msg.isStreaming" class="agent-streaming">
            <span class="dot-pulse"></span>
          </div>
        </div>
      </div>
      <div class="agent-input-area">
        <div v-if="contextText" class="agent-context-note">
          已使用编辑器{{ editorSelection.text ? '选区' : '文档' }}作为上下文（{{ contextText.length }} 字符）
        </div>
        <!-- File attachments -->
        <div class="agent-attachments" v-if="files.length">
          <div class="agent-file" v-for="f in files" :key="f.name">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
            <span>{{ f.name }}</span>
            <button class="agent-file-remove" title="移除附件" @click="removeFile(f.name)">×</button>
          </div>
        </div>
        <div class="agent-input-row">
          <button class="agent-attach-btn" @click="attachFile" title="添加附件" :disabled="sending">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
          </button>
          <input
            v-model="input"
            @keydown.enter="sendMessage"
            :disabled="sending"
            placeholder="输入消息..."
            class="agent-input"
          />
          <button class="agent-send-btn" @click="sendMessage" :disabled="sending || !input.trim()">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
            </svg>
          </button>
        </div>
      </div>
    </div>

    <!-- Docs Tab -->
    <div v-show="tab === 'docs'" class="agent-docs">
      <div class="docs-toolbar">
        <span class="docs-title">已入库文档</span>
        <div class="docs-toolbar-actions">
          <button class="btn primary" :disabled="ragUploading" @click="ragFileInput?.click()">
            {{ ragUploading ? '上传中...' : '上传文件' }}
          </button>
          <button class="btn ghost" @click="fetchDocs" :disabled="ragLoading">刷新</button>
        </div>
        <input ref="ragFileInput" type="file" style="display:none"
          accept=".pdf,.docx,.doc,.txt,.md,.log,.html,.htm,.epub,.rtf,.tex,.csv,.pptx,.xlsx,.srt,.json,.xml"
          @change="handleRagUpload" />
      </div>
      <div v-if="ragUploadError" class="docs-error">{{ ragUploadError }}</div>
      <div v-if="ragLoading" class="docs-loading">加载中...</div>
      <div v-else-if="ragDocuments.length === 0" class="docs-empty">暂无文档</div>
      <div v-else class="docs-list">
        <div v-for="doc in ragDocuments" :key="doc.id" class="doc-card">
          <div class="doc-info">
            <span class="doc-title">{{ doc.title || doc.id }}</span>
            <span class="doc-meta">{{ doc.chunk_count }} 块</span>
          </div>
          <button class="doc-del-btn" @click="deleteDoc(doc.id)" title="删除">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
            </svg>
          </button>
        </div>
      </div>
    </div>

    <!-- Templates Tab -->
    <div v-show="tab === 'templates'" class="agent-templates">
      <div class="docs-toolbar">
        <span class="docs-title">论文模板库</span>
        <button class="btn ghost" @click="loadPaperTemplates" :disabled="templatesLoading">刷新</button>
      </div>
      <div v-if="templatesLoading" class="docs-loading">加载中...</div>
      <div v-else-if="templates.length === 0" class="docs-empty">
        暂无模板数据
        <button class="btn ghost" style="margin-top:8px" @click="ingestPaperAssets">索引模板素材</button>
      </div>
      <div v-else class="template-grid">
        <div v-for="t in templates" :key="t.id" class="template-card" @click="previewingTemplate = t">
          <span class="template-icon">{{ t.icon }}</span>
          <div class="template-info">
            <span class="template-name">{{ t.name }}</span>
            <span class="template-venue">{{ t.venue }}</span>
          </div>
        </div>
      </div>
      <div v-if="previewingTemplate" class="template-preview">
        <div class="template-preview-header">
          <span>{{ previewingTemplate.icon }} {{ previewingTemplate.name }}</span>
          <button class="btn ghost" @click="previewingTemplate = null">&times;</button>
        </div>
        <div class="template-preview-desc">{{ previewingTemplate.description }}</div>
        <button class="btn primary" style="margin-top:8px;width:100%" @click="createFromTemplate(previewingTemplate)">以此为模板新建</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useAgentChat } from '../composables/useAgentChat'
import { useEditor } from '../composables/useEditor'
import AgentApprovalInline from './AgentApprovalInline.vue'
import AgentSessionList from './AgentSessionList.vue'
import { Pin, PinOff } from './ui/icons'
import { API_BASE } from '../utils/api'
import { WebviewWindow } from '@tauri-apps/api/webviewWindow'
import { getCurrentWindow } from '@tauri-apps/api/window'
import type { AgentSessionInfo } from '../types'

const props = defineProps<{
  open: boolean
  standalone?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
  (e: 'switch-to-editor'): void
}>()

// ── Real OS window float (Tauri) ──────────────────────────────────────────────

let _agentWindow: WebviewWindow | null = null
let _toggleGuard = false

async function openAgentWindow() {
  try {
    // Build URL with session ID if available — use absolute URL for dev mode
    const params = new URLSearchParams({ 'agent-only': '1' })
    if (sessionId.value) {
      params.set('session', sessionId.value)
    }

    // Signal to the new window that it's agent-only mode via localStorage.
    // Include a timestamp so stale flags from crashed sessions are ignored.
    const sid = sessionId.value || '1'
    sessionStorage.setItem('agent-mode-pending', `${Date.now()}|${sid}`)
    const url = `${window.location.origin}/`

    // If a previous agent window exists, close it first
    try { const old = await WebviewWindow.getByLabel('agent'); if (old) await old.close(); } catch {}

    _agentWindow = new WebviewWindow('agent', {
      url,
      title: 'Agent 助手',
      width: 400,
      height: 560,
      minWidth: 340,
      minHeight: 400,
      resizable: true,
      decorations: false,
      shadow: false,
      center: true,
      visible: true,
      skipTaskbar: true,
    })

    // Wait for the window to actually be created on the Rust side
    await new Promise<void>((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error('Window creation timed out')), 5000)
      _agentWindow!.once('tauri://created', () => {
        clearTimeout(timeout)
        resolve()
      })
      _agentWindow!.once('tauri://error', (e) => {
        clearTimeout(timeout)
        reject(new Error(String(e)))
      })
    })

    // When the agent window is destroyed (user closed via dock-back),
    // restore the inline panel in the main window
    _agentWindow.once('tauri://destroyed', () => {
      _agentWindow = null
      if (!isStandalone.value) {
        emit('update:open', true)
      }
    })

    // Hide the inline panel (deferred to avoid double-click from reactive re-render)
    await new Promise(r => setTimeout(r, 100))
    emit('update:open', false)
    localStorage.setItem('agent-float', '1')
  } catch (err) {
    console.error('Failed to open agent window:', err)
    _agentWindow = null
    sessionStorage.removeItem('agent-mode-pending')
  }
}

async function closeAgentWindow() {
  try {
    const w = await WebviewWindow.getByLabel('agent')
    if (w) {
      await w.close()
    }
  } catch (err) {
    console.warn('Close agent window failed:', err)
  }
  _agentWindow = null
  if (!isStandalone.value) {
    emit('update:open', true)
  }
  localStorage.setItem('agent-float', '0')
}

function toggleFloat() {
  if (_toggleGuard) return
  _toggleGuard = true
  try {
    if (_agentWindow) {
      closeAgentWindow()
    } else {
      openAgentWindow()
    }
  } finally {
    setTimeout(() => { _toggleGuard = false }, 500)
  }
}

// ── Standalone mode: read session from URL ────────────────────────────────────
const isStandalone = computed(() => props.standalone === true)

// Window drag for frameless standalone window
function onHeaderMouseDown(e: MouseEvent) {
  if (!isStandalone.value) return
  // Don't start drag when clicking on buttons
  const target = e.target as HTMLElement
  if (target.closest('button')) return
  getCurrentWindow().startDragging()
}

// Dock back: close standalone window, signal main window to restore inline panel
async function onDockBack() {
  localStorage.setItem('agent-dock-back', Date.now().toString())
  await getCurrentWindow().close()
}

// Listen for dock-back signal from standalone window
let _unlistenStorage: (() => void) | null = null

onMounted(async () => {
  if (isStandalone.value) {
    // Read session ID from localStorage and resume session
    const sid = localStorage.getItem('agent-session')
    localStorage.removeItem('agent-session')
    if (sid) {
      await resumeSession(sid)
    }
  } else {
    // Main window: listen for dock-back signal from standalone window
    const handler = (e: StorageEvent) => {
      if (e.key === 'agent-dock-back' && e.newValue) {
        localStorage.removeItem('agent-dock-back')
        emit('update:open', true)
      }
    }
    window.addEventListener('storage', handler)
    _unlistenStorage = () => window.removeEventListener('storage', handler)
  }
})


const {
  messages, sending, sessionId, pendingApproval,
  ragDocuments, ragLoading,
  sendMessage: agentSendMessage,
  stopGenerating, clearHistory,
  sendApproval, abortSession,
  resumeSession,
  fetchSessions: _fetchSessions,
  fetchRAGDocuments: _fetchRAGDocs,
  deleteRAGDocument,
  uploadRAGFile,
} = useAgentChat()

const { selection: editorSelection, content: editorContent, activeTab: editorActiveTab } = useEditor()

const tab = ref<'chat' | 'docs' | 'templates' | 'sessions'>('chat')
const input = ref('')
const messagesRef = ref<HTMLElement | null>(null)
const sessionListRef = ref<InstanceType<typeof AgentSessionList> | null>(null)
// 自动滚动：用户未手动上滚时保持跟底
const _userScrolledUp = ref(false)

function _scrollToBottom(smooth = false) {
  const el = messagesRef.value
  if (!el) return
  el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'instant' })
}

function _onMessagesScroll() {
  const el = messagesRef.value
  if (!el) return
  // 距离底部 60px 以内视为"在底部"
  const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 60
  _userScrolledUp.value = !atBottom
}
const sessions = ref<AgentSessionInfo[]>([])
const files = ref<{ name: string; content: string }[]>([])
const ragFileInput = ref<HTMLInputElement | null>(null)
const ragUploading = ref(false)
const ragUploadError = ref('')

const contextText = computed(() => {
  if (!editorActiveTab.value) return ''
  return editorSelection.value.text || editorContent.value
})

async function handleRagUpload() {
  const fileInput = ragFileInput.value
  if (!fileInput?.files?.length) return
  const file = fileInput.files[0]
  ragUploading.value = true
  ragUploadError.value = ''
  const result = await uploadRAGFile(file)
  ragUploading.value = false
  if (!result.ok) {
    ragUploadError.value = result.error || '上传失败'
    setTimeout(() => { ragUploadError.value = '' }, 4000)
  }
  fileInput.value = ''
}

// ── Tool descriptions ──
const TOOL_DESCRIPTIONS: Record<string, string> = {
  translate_text: '翻译文本为指定语言',
  parse_document: '解析文档文件，提取纯文本内容',
  search_documents: '在已入库文档中检索相关内容',
  crawl_arxiv: '搜索 arXiv 学术论文',
  polish_text: '润色文本，使其更加学术化',
  generate_outline: '根据研究主题生成论文大纲',
  summarize_text: '对长文本进行摘要',
  save_file: '将文本内容保存到文件',
  read_file: '读取文本文件内容',
  search_paper_templates: '检索论文模板和写作范例',
}

function getToolDescription(toolName?: string): string {
  if (!toolName) return ''
  return TOOL_DESCRIPTIONS[toolName] || ''
}

function formatToolArgs(args: Record<string, unknown>): string {
  const entries = Object.entries(args)
  if (!entries.length) return ''
  return entries
    .map(([k, v]) => {
      const val = typeof v === 'string' ? `"${v.length > 40 ? v.slice(0, 40) + '…' : v}"` : JSON.stringify(v)
      return `${k}: ${val}`
    })
    .join('\n')
}

function truncateResult(content: string): string {
  if (!content) return ''
  if (content.length <= 300) return content
  return content.slice(0, 300) + '…'
}

// ── Current status from streaming events ──
const currentStatus = computed(() => {
  const streaming = messages.value.find(m => m.isStreaming)
  if (!streaming) return ''
  if (pendingApproval.value) return '等待审批: ' + pendingApproval.value.tool_name
  for (let i = streaming.events.length - 1; i >= 0; i--) {
    const evt = streaming.events[i]
    if (evt.type === 'thinking' || evt.type === 'thought') return 'Thinking... ' + (evt.content.length > 100 ? evt.content.slice(0, 100) + '...' : evt.content)
    if (evt.type === 'tool_call') return 'Calling ' + ((evt.metadata?.tool_name || evt.metadata?.tool || evt.content) as string)
    if (evt.type === 'tool_result') return 'Done: ' + ((evt.metadata?.tool_name || evt.metadata?.tool || 'tool') as string)
    if (evt.type === 'task_started') return 'Starting task: ' + (evt.metadata?.title || '')
    if (evt.type === 'task_done') return 'Task completed'
    if (evt.type === 'warning') return 'Warning: ' + evt.content
  }
  return ''
})

// ── Approval ──
async function handleApprovalDecision(decision: 'allow_once' | 'allow_session' | 'deny') {
  const pending = pendingApproval.value
  if (!pending) return
  await sendApproval(pending.event_id, decision)
}

// ── Sessions ──
async function refreshSessions() {
  sessions.value = await _fetchSessions()
  sessionListRef.value?.fetchSessions()
}

async function handleSessionResume(sessionId: string) {
  await resumeSession(sessionId)
  tab.value = 'chat'
  _userScrolledUp.value = false
  await nextTick()
  _scrollToBottom()
}

// ── Send message ──
async function sendMessage() {
  const text = input.value.trim()
  if (!text || sending.value) return
  input.value = ''

  // Build full message with file contents
  let fullMsg = text
  if (files.value.length) {
    const ctx = files.value.map(f => `--- File: ${f.name} ---\n${f.content.slice(0, 12000)}\n--- End ---`).join('\n\n')
    fullMsg = `${ctx}\n\n${text}`
    files.value = []
  }

  await agentSendMessage(fullMsg, contextText.value, '')
  await nextTick()
  _scrollToBottom()
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

async function fetchDocs() {
  await _fetchRAGDocs()
}

async function deleteDoc(id: string) {
  await deleteRAGDocument(id)
}

// ── Paper templates ──
const templates = ref<{ id: string; name: string; venue: string; description: string; icon: string }[]>([])
const templatesLoading = ref(false)
const previewingTemplate = ref<{ id: string; name: string; venue: string; description: string; icon: string } | null>(null)

async function loadPaperTemplates() {
  templatesLoading.value = true
  try {
    const resp = await fetch(`${API_BASE}/api/paper-assets/templates`)
    if (resp.ok) {
      const data = await resp.json()
      templates.value = data.templates || []
    }
  } catch (e) { console.warn('loadPaperTemplates failed:', e) }
  finally { templatesLoading.value = false }
}

async function ingestPaperAssets() {
  try {
    await fetch(`${API_BASE}/api/paper-assets/ingest`, { method: 'POST' })
    loadPaperTemplates()
  } catch (e) { console.warn('ingestPaperAssets failed:', e) }
}

function createFromTemplate(t: any) {
  tab.value = 'chat'
  fetch(`${API_BASE}/api/paper-scaffold`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ template_id: t.id, title: '' }),
  }).then(r => r.json()).then(data => {
    if (data.markdown) {
      window.dispatchEvent(new CustomEvent('paper-scaffold', { detail: { markdown: data.markdown, templateId: t.id } }))
    }
  }).catch(() => {})
  previewingTemplate.value = null
}

// ── Watchers ──
watch(() => props.open, async (isOpen) => {
  if (isOpen) await fetchDocs()
})

watch(tab, (t) => {
  if (t === 'templates' && templates.value.length === 0) loadPaperTemplates()
})

// 流式输出自动跟底：监听 messages 深度变化，若用户没有手动上滚则自动滚底
watch(
  messages,
  async () => {
    if (_userScrolledUp.value) return
    await nextTick()
    _scrollToBottom()
  },
  { deep: true },
)

// 发送新消息时强制重置到底部（无论用户之前是否上滚）
watch(sending, (nowSending) => {
  if (nowSending) {
    _userScrolledUp.value = false
    nextTick(() => _scrollToBottom())
  }
})

onMounted(() => {
  messagesRef.value?.addEventListener('scroll', _onMessagesScroll, { passive: true })
})

onUnmounted(() => {
  messagesRef.value?.removeEventListener('scroll', _onMessagesScroll)
  _unlistenStorage?.()
  _unlistenStorage = null
})
</script>

<style scoped>
.agent-panel {
  position: fixed; top: 0; right: 0;
  width: min(420px, 100vw); height: calc(100vh - 62px);
  margin-top: 62px;
  background: var(--c-glass);
  border-left: none;
  box-shadow: -20px 0 80px rgba(0, 0, 0, 0.4), inset 1px 0 0 rgba(255, 255, 255, 0.05);
  backdrop-filter: blur(32px);
  -webkit-backdrop-filter: blur(32px);
  display: flex; flex-direction: column;
  z-index: 200;
  transform: translateX(100%);
  transition: transform var(--motion-page, 320ms) var(--ease-spring);
}
.agent-panel.open { transform: translateX(0); }

/* Standalone mode: rounded floating panel look, drag header */
.agent-panel.standalone {
  position: relative;
  width: 100%;
  height: 100vh;
  right: auto;
  top: auto;
  margin-top: 0;
  transform: none !important;
  border-radius: var(--radius-xl);
  border: 1px solid var(--c-glass-border);
  box-shadow: var(--elevation-4);
  overflow: hidden;
}
.agent-header.window-drag {
  cursor: grab;
}
.agent-header.window-drag:active {
  cursor: grabbing;
}

.agent-header {
  display: flex; align-items: center; gap: 6px;
  padding: 16px 20px 12px;
  border-bottom: none;
  background: linear-gradient(to bottom, var(--c-surface-1) 0%, transparent 100%);
  flex-shrink: 0;
}

.agent-tabs {
  display: flex; gap: 4px; flex: 1;
  background: rgba(0, 0, 0, 0.2);
  padding: 4px;
  border-radius: 12px;
}
.agent-tab {
  padding: 6px 14px; border: none; border-radius: 8px;
  font-size: 12px; font-weight: 600; cursor: pointer;
  background: transparent; color: var(--c-text-2);
  transition: all var(--motion-fast);
  white-space: nowrap;
}
.agent-tab:hover { color: var(--c-text-0); }
.agent-tab.active {
  background: var(--c-surface-3);
  color: var(--c-text-0);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.08);
}

.agent-header-actions { display: flex; align-items: center; gap: 2px; flex-shrink: 0; }

.agent-hdr-btn {
  display: flex; align-items: center; justify-content: center;
  width: 26px; height: 26px;
  background: none; border: none; color: var(--c-text-3);
  cursor: pointer; border-radius: 4px;
  transition: all var(--motion-fast);
}
.agent-hdr-btn:hover { color: var(--c-text-0); background: var(--c-surface-2); }

.agent-close-btn {
  background: none; border: none; color: var(--c-text-3);
  cursor: pointer; padding: 4px; border-radius: 4px;
  display: flex; align-items: center;
  transition: all var(--motion-fast);
}
.agent-close-btn:hover { color: var(--c-text-0); background: var(--c-surface-2); }

.agent-chat {
  flex: 1; display: flex; flex-direction: column; overflow: hidden;
  background: linear-gradient(to bottom, transparent, rgba(0,0,0,0.1));
}
.agent-messages {
  flex: 1; overflow-y: auto; padding: 24px 20px;
  display: flex; flex-direction: column; gap: 24px;
}
.agent-empty { text-align: center; color: var(--c-text-3); padding: 40px 20px; }
.agent-empty p:first-child {
  font-family: var(--font-serif);
  font-style: italic;
  font-size: 15px;
  color: var(--c-text-2);
}
.agent-empty .hint { font-size: 12px; }

.agent-msg { max-width: 92%; }
.agent-msg.user { align-self: flex-end; }
.agent-msg.assistant { align-self: flex-start; max-width: 100%; }

.agent-bubble {
  padding: 10px 14px; border-radius: 12px;
  font-size: 14px; line-height: 1.6;
  white-space: pre-wrap; word-break: break-word;
}
.agent-msg.user .agent-bubble {
  background: var(--c-accent); color: #fff;
  border-radius: 16px 16px 4px 16px;
  padding: 12px 18px;
  box-shadow: 0 8px 24px var(--accent-glow);
}
.agent-msg.assistant .agent-bubble {
  background: transparent; color: var(--c-text-0);
  padding: 4px 8px;
  border-radius: 0;
  font-size: 14.5px;
  line-height: 1.7;
}

/* Event stream — ink-styled cards */
.agent-event {
  font-size: 12px; padding: 8px 12px;
  margin-bottom: 8px; border-radius: 10px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(8px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  position: relative;
  animation: evt-fade-in var(--motion-base) var(--ease-out);
}
@keyframes evt-fade-in {
  from { opacity: 0; transform: translateY(4px); }
  to   { opacity: 1; transform: translateY(0); }
}
/* @property enables smooth mask-image gradient interpolation */
@property --ink-stop {
  syntax: '<percentage>';
  inherits: false;
  initial-value: 0%;
}

.agent-event.thinking {
  --ink-stop: 100%;
  color: var(--c-text-2); display: flex; align-items: flex-start; gap: 6px;
  font-style: normal; border-left: 2px solid var(--accent-0);
  mask-image: linear-gradient(to bottom, #000 var(--ink-stop), transparent calc(var(--ink-stop) + 16px));
  -webkit-mask-image: linear-gradient(to bottom, #000 var(--ink-stop), transparent calc(var(--ink-stop) + 16px));
  animation: evt-ink-bleed 400ms var(--ease-out) both;
}
@keyframes evt-ink-bleed {
  from { --ink-stop: 0%; opacity: 0.3; }
  to   { --ink-stop: 100%; opacity: 1; }
}
.agent-event.tool-call {
  border-left: 2px solid #3b82f6; background: color-mix(in srgb, #3b82f6 6%, var(--c-surface-1));
  animation: evt-slide-in-left 240ms var(--ease-out);
}
@keyframes evt-slide-in-left {
  from { opacity: 0; transform: translateX(-16px); }
  to   { opacity: 1; transform: translateX(0); }
}
.agent-event.tool-result {
  border-left: 2px solid var(--c-success); background: color-mix(in srgb, var(--c-success) 6%, var(--c-surface-1));
  animation: evt-scale-in 240ms var(--ease-spring);
}
@keyframes evt-scale-in {
  from { opacity: 0; transform: scale(0.96); }
  to   { opacity: 1; transform: scale(1); }
}
.agent-event.tool-result.evt-error {
  border-left: 2px solid var(--vermilion-0); background: color-mix(in srgb, var(--vermilion-0) 6%, var(--c-surface-1));
  animation: evt-shake 300ms var(--ease-out);
}
@keyframes evt-shake {
  0%, 100% { transform: translateX(0); }
  20% { transform: translateX(-3px); }
  40% { transform: translateX(3px); }
  60% { transform: translateX(-1px); }
}

.evt-label {
  font-weight: 600; font-size: 11px; text-transform: uppercase;
  color: var(--c-text-2); flex-shrink: 0;
}
.evt-thinking-dot {
  width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0;
  background: var(--accent-0); animation: dot-breathe 1.6s ease-in-out infinite;
}
@keyframes dot-breathe {
  0%, 100% { opacity: 0.3; transform: scale(0.85); }
  50% { opacity: 1; transform: scale(1); }
}
.evt-content-text { color: var(--c-text-2); }
.evt-tool-header { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.evt-tool-icon { font-size: 13px; flex-shrink: 0; }
.evt-tool-icon.success { color: var(--c-success); }
.evt-tool-icon.error { color: var(--c-danger); }
.evt-tool-name { font-weight: 600; color: var(--c-accent); font-size: 13px; }
.evt-tool-desc { font-size: 11px; color: var(--c-text-2); margin: 2px 0 5px 22px; }
.evt-tool-args {
  background: var(--c-surface-2); border-radius: 4px; padding: 5px 8px;
  margin-top: 4px; border: 1px solid var(--c-surface-3);
}
.evt-args-label { font-size: 10px; color: var(--c-text-3); text-transform: uppercase; font-weight: 600; margin-right: 6px; }
.evt-args-code { font-size: 11px; color: var(--c-text-2); white-space: pre-wrap; word-break: break-all; }
.evt-result-header { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.evt-result-tool { font-weight: 600; color: var(--c-text-2); font-size: 12px; }
.evt-duration { font-size: 11px; color: var(--c-text-3); margin-left: auto; }
.evt-result-preview { font-size: 11px; color: var(--c-text-2); line-height: 1.5; white-space: pre-wrap; word-break: break-word; max-height: 80px; overflow: hidden; }

/* Task lifecycle */
.agent-event.task-lifecycle {
  display: flex; align-items: center; gap: 6px;
  border-left: 2px solid var(--c-accent); background: color-mix(in srgb, var(--c-accent) 6%, var(--c-surface-1));
}
.agent-event.task-lifecycle.done {
  border-left-color: var(--c-success); background: color-mix(in srgb, var(--c-success) 6%, var(--c-surface-1));
}
.evt-lifecycle-icon { font-size: 14px; flex-shrink: 0; }
.evt-task-title { font-size: 13px; font-weight: 500; color: var(--c-text-0); }
.evt-task-id { font-size: 11px; color: var(--c-text-3); font-family: monospace; }
.evt-task-progress {
  font-size: 11px; color: var(--c-accent-hover);
  margin-left: auto; font-variant-numeric: tabular-nums; font-weight: 600;
}

/* Risk badge */
.evt-risk-badge { font-size: 9px; text-transform: uppercase; font-weight: 600; padding: 1px 5px; border-radius: 3px; }
.evt-risk-badge.risk-safe { background: rgba(74, 222, 128, 0.15); color: var(--c-success); }
.evt-risk-badge.risk-moderate { background: rgba(245, 158, 11, 0.15); color: var(--c-warn); }
.evt-risk-badge.risk-destructive { background: rgba(248, 113, 113, 0.15); color: var(--c-danger); }
.evt-risk-badge.risk-banned { background: var(--c-surface-0); color: var(--c-danger); }

/* Warning */
.agent-event.warning {
  display: flex; align-items: center; gap: 8px;
  border-left: 2px solid var(--c-warn);
  background: color-mix(in srgb, var(--c-warn) 6%, var(--c-surface-1));
}
.evt-warning-icon { font-size: 14px; flex-shrink: 0; color: var(--c-warn); }

.agent-sessions { flex: 1; overflow-y: auto; padding: 0; }

.agent-status-bar {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 14px; margin-bottom: 8px;
  background: color-mix(in srgb, var(--c-accent) 12%, var(--c-surface-1));
  border: 1px solid color-mix(in srgb, var(--c-accent) 30%, transparent);
  border-radius: 20px; width: fit-content; max-width: 100%;
}
.agent-status-text { font-size: 12px; color: var(--c-text-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 260px; }

.agent-streaming { display: flex; padding: 8px 14px; }
.dot-pulse {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--c-accent); animation: dot-pulse 1.2s infinite;
}
@keyframes dot-pulse {
  0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); }
  40% { opacity: 1; transform: scale(1); }
}

/* Input area — suspended inkstone */
.agent-input-area {
  display: flex; flex-direction: column; gap: 8px;
  padding: 16px 20px 24px;
  border-top: none;
  background: linear-gradient(to top, var(--c-surface-1) 40%, transparent 100%);
  position: relative;
}
.agent-context-note { width: 100%; color: var(--c-text-3); font-size: 11px; }
.agent-input-row {
  width: 100%; display: flex; gap: 6px; align-items: center;
  background: var(--c-surface-2);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 24px;
  padding: 6px;
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.3), inset 0 1px 1px rgba(255, 255, 255, 0.05);
  transition: all var(--motion-slow) var(--ease-out);
}
.agent-input-row:focus-within {
  border-color: rgba(91, 108, 255, 0.4);
  box-shadow: 0 16px 48px rgba(91, 108, 255, 0.15), inset 0 1px 1px rgba(255, 255, 255, 0.1);
  background: var(--c-surface-3);
}
.agent-input {
  flex: 1; padding: 8px 12px;
  border: none;
  background: transparent;
  color: var(--c-text-0); font-size: 14px; font-family: inherit;
  outline: none; box-shadow: none;
}
.agent-input:focus { border-color: transparent; }
.agent-input:disabled { opacity: 0.5; }
.agent-attach-btn {
  width: 36px; height: 36px;
  border-radius: 50%;
  border: none;
  background: transparent; color: var(--c-text-2);
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; transition: all 0.15s;
}
.agent-attach-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.05); color: var(--c-text-0);
}
.agent-attach-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.agent-send-btn {
  width: 36px; height: 36px;
  border-radius: 50%;
  border: none;
  background: var(--c-accent); color: #fff; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 4px 12px var(--accent-glow);
  transition: opacity 0.15s;
}
.agent-send-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.agent-send-btn:not(:disabled):hover { opacity: 0.85; }

/* File attachments */
.agent-attachments {
  width: 100%; display: flex; gap: 6px; flex-wrap: wrap;
  padding: 6px 0;
}
.agent-file {
  display: flex; align-items: center; gap: 4px;
  background: var(--c-surface-2); border: 1px solid var(--c-surface-3);
  border-radius: 4px; padding: 3px 8px; font-size: 11px; color: var(--c-text-3);
}
.agent-file svg { flex-shrink: 0; }
.agent-file-remove {
  background: none; border: none; color: var(--c-text-3);
  cursor: pointer; font-size: 14px; line-height: 1; padding: 0 2px;
}
.agent-file-remove:hover { color: var(--c-danger); }

/* Docs tab */
.agent-docs { flex: 1; overflow-y: auto; padding: 16px; }
.docs-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.docs-toolbar-actions { display: flex; gap: 6px; }
.docs-error { text-align: center; color: var(--c-danger); font-size: 12px; padding: 8px; background: var(--c-danger-bg); border-radius: 6px; margin-bottom: 8px; }
.docs-title { font-size: 13px; font-weight: 600; color: var(--c-text-0); }
.docs-loading, .docs-empty { text-align: center; color: var(--c-text-3); padding: 40px; }
.docs-list { display: flex; flex-direction: column; gap: 8px; }
.doc-card {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 12px; background: var(--c-surface-2);
  border: 1px solid var(--c-surface-3); border-radius: 8px;
}
.doc-info { display: flex; flex-direction: column; gap: 2px; }
.doc-title { font-size: 13px; color: var(--c-text-0); }
.doc-meta { font-size: 11px; color: var(--c-text-3); }
.doc-del-btn {
  background: none; border: none; color: var(--c-text-3);
  cursor: pointer; padding: 4px; border-radius: 4px;
  display: flex; align-items: center;
}
.doc-del-btn:hover { color: var(--c-danger); background: var(--c-danger-bg); }

/* Templates tab */
.agent-templates { flex: 1; overflow-y: auto; padding: 16px; }
.template-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; }
.template-card {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 12px; background: var(--c-surface-2);
  border: 1px solid var(--c-surface-3); border-radius: 8px;
  cursor: pointer; transition: all 0.15s;
}
.template-card:hover { border-color: var(--c-accent-hover); background: var(--c-accent-bg2); }
.template-icon { font-size: 24px; }
.template-info { display: flex; flex-direction: column; gap: 1px; }
.template-name { font-size: 13px; font-weight: 600; color: var(--c-text-0); }
.template-venue { font-size: 11px; color: var(--c-text-3); }
.template-preview {
  margin-top: 12px; padding: 12px;
  background: var(--c-surface-2); border: 1px solid var(--c-surface-3);
  border-radius: 8px;
}
.template-preview-header {
  display: flex; justify-content: space-between; align-items: center;
  font-size: 14px; font-weight: 600; color: var(--c-text-0);
}
.template-preview-desc { font-size: 12px; color: var(--c-text-3); margin-top: 6px; line-height: 1.5; }

/* Buttons (docs/templates tabs) */
.btn {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 5px 12px; border: none; border-radius: 6px;
  font-size: 13px; font-weight: 500; cursor: pointer;
  transition: all 0.15s; font-family: inherit;
}
.btn.ghost { background: transparent; color: var(--c-text-2); }
.btn.ghost:hover { color: var(--c-accent-hover); }
.btn.ghost:disabled { opacity: 0.4; cursor: not-allowed; }
.btn.primary { background: var(--c-accent); color: #fff; }
.btn.primary:hover { opacity: 0.88; }
</style>
