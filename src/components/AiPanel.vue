<template>
  <div class="ai-panel">
    <div class="ai-header">
      <span class="ai-title">AI Assist</span>
      <div class="header-actions">
        <div class="mode-toggle">
          <button :class="{ active: !isAgentMode }" @click="isAgentMode = false" title="Assistant Mode">Assis</button>
          <button :class="{ active: isAgentMode }" @click="isAgentMode = true" title="Agent Mode (RAG+ReAct)">Agent</button>
        </div>
        <button class="ai-btn-icon" @click="handleUndo" title="撤销上次插入" :disabled="!canUndo">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7v6h6"/><path d="M21 17a9 9 0 00-15-6.7L3 13"/></svg>
        </button>
        <button class="ai-close" @click="$emit('close')" title="关闭面板">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
        </button>
      </div>
    </div>

    <div class="ai-body">
      <!-- 已挂载的文件 -->
      <div class="ai-attachments" v-if="attachedFiles.length">
        <div class="ai-attachment" v-for="f in attachedFiles" :key="f.path">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
          <span class="attachment-name">{{ f.name }}</span>
          <button class="attachment-remove" @click="removeAttachment(f.path)">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
      </div>

      <!-- 指令输入 -->
      <div class="ai-input-area">
        <textarea
          ref="inputRef"
          v-model="instruction"
          class="ai-input"
          placeholder="输入指令，例如：帮我扩写这段、翻译成英文、检查语法..."
          @keydown.enter.ctrl="handleSend"
          :disabled="loading"
          rows="3"
        />
        <div class="ai-input-actions">
          <span class="ai-hint">Ctrl+Enter 发送</span>
          <div style="flex:1"></div>
          <button class="ai-attach" @click="handleAttachFile" title="附加文件作为上下文" :disabled="loading">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"/></svg>
            附加文件
          </button>
          <!-- 发送 / 取消 -->
          <button v-if="!loading" class="ai-send" @click="handleSend" :disabled="!instruction.trim()">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4z"/></svg>
            发送
          </button>
          <button v-else class="ai-cancel" @click="handleCancel">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/></svg>
            取消
          </button>
        </div>
      </div>

      <!-- 快捷预设 -->
      <div class="ai-presets">
        <button class="ai-preset" @click="runPreset('请扩写以下文本，增加更多细节和学术深度，使其成为完整详尽的学术段落。', 'expand')">扩写</button>
        <button class="ai-preset" @click="runPreset('请润色以下学术文本，提升语法、词汇和学术风格，使表达更正式、简洁、流畅。', 'polish')">润色</button>
        <button class="ai-preset" @click="runPreset('请审查以下学术文本，找出潜在问题并提出改进建议，包括逻辑连贯性、论证充分性和语言表达。', 'polish')">审查</button>
        <button class="ai-preset" @click="runPreset('请将以下中文文本翻译为流畅的学术英文，保持原意，提升学术规范性。', 'expand')">英译</button>
        <button class="ai-preset" @click="runPreset('Please translate the following text into fluent academic Chinese, preserving the original meaning.', 'expand')">中译</button>
      </div>

      <!-- 风格迁移预设 -->
      <div class="ai-style-presets">
        <span class="ai-style-label">风格迁移:</span>
        <button class="ai-preset style-preset" @click="runStyleTransfer('neurips')">NeurIPS</button>
        <button class="ai-preset style-preset" @click="runStyleTransfer('ieee_conference')">IEEE</button>
        <button class="ai-preset style-preset" @click="runStyleTransfer('acm')">ACM</button>
        <button class="ai-preset style-preset" @click="runStyleTransfer('lncs')">LNCS</button>
      </div>

      <!-- 加载状态 -->
      <div class="ai-loading" v-if="loading">
        <span class="ai-spinner"></span>
        <span>AI 正在处理...</span>
      </div>

      <!-- AI 结果 -->
      <div class="ai-result" v-if="result && !loading">
        <div class="ai-label">AI Response</div>
        <div class="ai-result-text" v-html="renderedResult"></div>
        <div class="ai-actions">
          <button class="ai-action accept" @click="handleAccept">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
            插入到编辑器
          </button>
          <button class="ai-action discard" @click="handleReject">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            丢弃
          </button>
        </div>
      </div>

      <!-- 提示信息 -->
      <div class="ai-notice" v-if="notice">
        {{ notice }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import DOMPurify from 'dompurify'

const props = defineProps<{
  loading: boolean
  result: string
  canUndo?: boolean
}>()

const emit = defineEmits<{
  (e: 'edit', instruction: string, taskType?: string): void
  (e: 'accept'): void
  (e: 'reject'): void
  (e: 'undo'): void
  (e: 'cancel'): void
  (e: 'close'): void
  (e: 'styleTransfer', templateId: string, templateName: string): void
  (e: 'agent', instruction: string): void
}>()

const instruction = ref('')
const inputRef = ref<HTMLTextAreaElement>()
const attachedFiles = ref<{ path: string; name: string; content: string }[]>([])
const notice = ref('')
const isAgentMode = ref(false)

function showNotice(msg: string) {
  notice.value = msg
  setTimeout(() => { notice.value = '' }, 3000)
}

async function handleAttachFile() {
  try {
    const { open } = await import('@tauri-apps/plugin-dialog')
    const selected = await open({ multiple: true, filters: [{ name: 'Text', extensions: ['md', 'txt', 'tex', 'pdf', 'py', 'js', 'ts', 'json', 'yaml', 'yml', 'xml', 'html', 'css'] }] })
    if (!selected) return
    const paths = Array.isArray(selected) ? selected : [selected]
    for (const path of paths) {
      if (attachedFiles.value.some(f => f.path === path)) continue
      const { readTextFile } = await import('@tauri-apps/plugin-fs')
      const fileContent = await readTextFile(path)
      const name = path.split(/[\\/]/).pop() || path
      attachedFiles.value.push({ path, name, content: fileContent })
    }
  } catch (e) {
    console.error('Failed to attach file:', e)
  }
}

function removeAttachment(path: string) {
  attachedFiles.value = attachedFiles.value.filter(f => f.path !== path)
}

function handleSend() {
  if (!instruction.value.trim() || props.loading) return
  let fullInstruction = instruction.value.trim()
  if (attachedFiles.value.length) {
    const filesCtx = attachedFiles.value.map(f =>
      `--- File: ${f.name} ---\n${f.content}\n--- End: ${f.name} ---`
    ).join('\n\n')
    fullInstruction = `${filesCtx}\n\nUser request: ${instruction.value.trim()}`
  }
  if (isAgentMode.value) {
    emit('agent', fullInstruction)
  } else {
    emit('edit', fullInstruction)
  }
}

function runPreset(presetInstruction: string, taskType?: string) {
  instruction.value = presetInstruction
  if (isAgentMode.value) {
    emit('agent', presetInstruction)
  } else {
    emit('edit', presetInstruction, taskType)
  }
}

async function runStyleTransfer(templateId: string) {
  const text = '' // The actual text will be sent from EditorLayout's selection
  const names: Record<string, string> = {
    neurips: 'NeurIPS',
    ieee_conference: 'IEEE',
    acm: 'ACM',
    lncs: 'LNCS',
  }
  const name = names[templateId] || templateId
  instruction.value = `适配 ${name} 风格`
  emit('styleTransfer', templateId, name)
}

function handleCancel() {
  emit('cancel')
}

function handleAccept() {
  emit('accept')
}

function handleReject() {
  instruction.value = ''
  attachedFiles.value = []
  emit('reject')
}

function handleUndo() {
  emit('undo')
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function renderMarkdown(text: string): string {
  const safe = escapeHtml(text)
  const html = safe
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`(.+?)`/g, '<code style="background:#2d2d2d;padding:1px 5px;border-radius:3px;font-size:0.9em">$1</code>')
    .replace(/\n/g, '<br/>')
  return DOMPurify.sanitize(html)
}

const renderedResult = computed(() => renderMarkdown(props.result))
</script>

<style scoped>
.ai-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--panel-bg);
  border-left: 1px solid var(--border-color);
}

.ai-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-color);
}

.ai-title {
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--text-secondary);
}

.header-actions { display: flex; align-items: center; gap: 6px; }

.mode-toggle {
  display: flex;
  background: var(--input-bg);
  border: 1px solid var(--border-color);
  border-radius: 4px;
  overflow: hidden;
}
.mode-toggle button {
  background: none;
  border: none;
  padding: 4px 8px;
  font-size: 10px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s;
}
.mode-toggle button.active {
  background: var(--accent);
  color: #fff;
}
.mode-toggle button:hover:not(.active) { background: var(--hover-bg); color: var(--text-primary); }

.ai-btn-icon {
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  display: flex;
  align-items: center;
}
.ai-btn-icon:hover { background: var(--hover-bg); color: var(--text-primary); }
.ai-btn-icon:disabled { opacity: 0.3; cursor: not-allowed; }

.ai-close {
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  display: flex;
}
.ai-close:hover { color: var(--text-primary); }

.ai-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.ai-label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.ai-input-area {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ai-input-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.ai-hint {
  font-size: 11px;
  color: var(--text-secondary);
  opacity: 0.6;
}

.ai-input {
  width: 100%;
  background: var(--input-bg);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 8px 12px;
  color: var(--text-primary);
  font-size: 13px;
  font-family: inherit;
  line-height: 1.5;
  resize: none;
  outline: none;
  box-sizing: border-box;
}
.ai-input:focus { border-color: var(--accent); }
.ai-input::placeholder { color: var(--text-secondary); font-size: 12px; }
.ai-input:disabled { opacity: 0.6; }

.ai-send {
  background: var(--accent);
  border: none;
  border-radius: 6px;
  padding: 6px 14px;
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  font-weight: 500;
}
.ai-send:hover { opacity: 0.9; }
.ai-send:disabled { opacity: 0.4; cursor: not-allowed; }

.ai-cancel {
  background: #da3633;
  border: none;
  border-radius: 6px;
  padding: 6px 14px;
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  font-weight: 500;
}
.ai-cancel:hover { opacity: 0.85; }

.ai-attach {
  background: var(--hover-bg);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 5px 10px;
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
}
.ai-attach:hover { background: var(--active-bg); color: var(--text-primary); }
.ai-attach:disabled { opacity: 0.4; cursor: not-allowed; }

.ai-attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.ai-attachment {
  display: flex;
  align-items: center;
  gap: 5px;
  background: var(--code-bg);
  border: 1px solid var(--border-color);
  border-radius: 4px;
  padding: 3px 8px;
  font-size: 11px;
  color: var(--text-secondary);
}

.attachment-name {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.attachment-remove {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--text-secondary);
  padding: 1px;
  display: flex;
  border-radius: 2px;
}
.attachment-remove:hover { color: var(--text-primary); background: var(--hover-bg); }

.ai-presets {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.ai-preset {
  background: var(--hover-bg);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 4px 12px;
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}
.ai-preset:hover { background: var(--active-bg); color: var(--text-primary); border-color: var(--accent); }

.ai-style-presets {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  padding-top: 6px;
}

.ai-style-label {
  font-size: 11px;
  color: var(--text-secondary);
  margin-right: 2px;
}

.style-preset {
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 10px;
  border-style: dashed;
  opacity: 0.8;
}
.style-preset:hover { opacity: 1; }

.ai-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 0;
  color: var(--text-secondary);
  font-size: 12px;
}

.ai-result {
  background: var(--code-bg);
  border: 1px solid var(--accent);
  border-radius: 6px;
  padding: 12px;
  flex: 1;
  overflow: auto;
}

.ai-result-text {
  font-size: 13px;
  color: var(--text-primary);
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 400px;
  overflow-y: auto;
}

.ai-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid var(--border-color);
}

.ai-action {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 6px 12px;
  border-radius: 4px;
  border: none;
  cursor: pointer;
  font-size: 12px;
  font-weight: 500;
  font-family: inherit;
}
.ai-action.accept { background: var(--green); color: #fff; }
.ai-action.accept:hover { opacity: 0.85; }
.ai-action.discard { background: var(--hover-bg); color: var(--text-secondary); }
.ai-action.discard:hover { background: #da3633; color: #fff; }

.ai-notice {
  padding: 8px 12px;
  background: rgba(255,193,7,0.1);
  border: 1px solid rgba(255,193,7,0.3);
  border-radius: 4px;
  color: #ffc107;
  font-size: 12px;
}

.ai-spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
