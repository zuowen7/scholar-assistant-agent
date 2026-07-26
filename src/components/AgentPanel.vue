<template>
  <div
    class="agent-panel"
    :class="{
      open: open && !isFloating,
      standalone: isStandalone,
      floating: isFloating,
      embedded: isEmbedded,
    }"
    :style="isFloating ? { left: floatX + 'px', top: floatY + 'px' } : {}"
    role="complementary"
    :aria-label="t('agent.title')"
    :aria-hidden="panelInactive ? 'true' : undefined"
    :inert="panelInactive"
  >
    <div
      class="agent-header"
      :class="{ draggable: isStandalone || isFloating }"
      @mousedown="_headerMouseDown"
    >
      <div class="agent-tabs" role="tablist" :aria-label="t('agent.title')" @keydown="onTabKeydown">
        <button
          id="agent-tab-chat"
          role="tab"
          aria-controls="agent-panel-chat"
          :aria-selected="tab === 'chat'"
          :tabindex="tab === 'chat' ? 0 : -1"
          class="agent-tab u-interactive"
          :class="{ active: tab === 'chat' }"
          @click="selectTab('chat')"
        >
          {{ t('agent.tabChat') }}
        </button>
        <button
          id="agent-tab-docs"
          role="tab"
          aria-controls="agent-panel-docs"
          :aria-selected="tab === 'docs'"
          :tabindex="tab === 'docs' ? 0 : -1"
          class="agent-tab u-interactive"
          :class="{ active: tab === 'docs' }"
          @click="selectTab('docs')"
        >
          {{ t('agent.tabDocs') }}
        </button>
        <button
          id="agent-tab-templates"
          role="tab"
          aria-controls="agent-panel-templates"
          :aria-selected="tab === 'templates'"
          :tabindex="tab === 'templates' ? 0 : -1"
          class="agent-tab u-interactive"
          :class="{ active: tab === 'templates' }"
          @click="selectTab('templates')"
        >
          {{ t('agent.tabSkills') }}
        </button>
        <button
          id="agent-tab-sessions"
          role="tab"
          aria-controls="agent-panel-sessions"
          :aria-selected="tab === 'sessions'"
          :tabindex="tab === 'sessions' ? 0 : -1"
          class="agent-tab u-interactive"
          :class="{ active: tab === 'sessions' }"
          @click="selectTab('sessions')"
        >
          {{ t('agent.tabSessions') }}
        </button>
      </div>
      <div class="agent-header-actions">
        <button
          v-if="tab === 'chat'"
          class="agent-hdr-btn"
          :title="t('agent.newSession')"
          :aria-label="t('agent.newSession')"
          :disabled="sending || !!pendingApproval"
          @click="handleNewSession"
        >
          <Plus :size="14" :stroke-width="1.8" />
        </button>
        <!-- Standalone window: dock back to main -->
        <button
          v-if="isStandalone"
          class="agent-hdr-btn"
          :title="t('agent.dockBack')"
          @click="onDockBack"
        >
          <PinOff :size="13" :stroke-width="1.8" />
        </button>
        <!-- Main window: float / dock toggle -->
        <button
          v-if="!isStandalone && !isEmbedded"
          class="agent-hdr-btn"
          :title="isFloating ? t('agent.dockSide') : t('agent.popFloat')"
          @click="toggleFloat"
        >
          <PinOff v-if="isFloating" :size="13" :stroke-width="1.8" />
          <Pin v-else :size="13" :stroke-width="1.8" />
        </button>
        <button
          v-if="!isStandalone && !isFloating"
          class="agent-close-btn"
          @click="$emit('update:open', false)"
          :aria-label="t('agent.close')"
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>
    </div>

    <!-- Sessions Tab -->
    <div
      id="agent-panel-sessions"
      v-show="tab === 'sessions'"
      role="tabpanel"
      aria-labelledby="agent-tab-sessions"
      class="agent-sessions"
    >
      <AgentSessionList ref="sessionListRef" @open="handleSessionOpen" />
    </div>

    <!-- Chat Tab -->
    <div
      id="agent-panel-chat"
      v-show="tab === 'chat'"
      role="tabpanel"
      aria-labelledby="agent-tab-chat"
      class="agent-chat"
    >
      <div v-if="sending && !pendingApproval" class="agent-thinking-bar"></div>
      <div class="agent-messages" ref="messagesRef" @scroll="_onMessagesScroll">
        <div v-if="currentStatus && sending && !pendingApproval" class="agent-status-bar">
          <span class="status-dots"><i></i><i></i><i></i></span>
          <span class="agent-status-text">{{ currentStatus }}</span>
        </div>
        <div v-if="messages.length === 0 && !sending" class="agent-empty">
          <p>{{ t('agent.placeholder') }}</p>
          <p class="hint" v-if="workspaceName">
            {{ t('agent.workspaceLabel') }}{{ workspaceName }}
          </p>
          <p class="hint warn" v-else>{{ t('agent.noWorkspaceLabel') }}</p>
        </div>
        <div v-for="msg in messages" :key="msg.id" class="agent-msg" :class="msg.role">
          <AgentThoughtGroup
            v-if="msg.role === 'assistant'"
            :events="msg.events"
            :streaming="msg.isStreaming"
          />
          <AgentExecutionGroup
            v-if="msg.role === 'assistant'"
            :events="msg.events"
            :streaming="msg.isStreaming"
          />
          <template v-for="(evt, i) in msg.events" :key="i">
            <div v-if="evt.type === 'task_started'" class="agent-event task-lifecycle">
              <span class="evt-lifecycle-icon">&#x25B6;</span>
              <span class="evt-label">{{ t('agent.labelTask') }}</span>
              <span class="evt-task-title">{{ evt.metadata?.title || evt.content }}</span>
              <span v-if="evt.metadata?.index != null" class="evt-task-progress"
                >{{ evt.metadata.index }}/{{ evt.metadata.total }}</span
              >
            </div>
            <div v-else-if="evt.type === 'task_done'" class="agent-event task-lifecycle done">
              <span class="evt-lifecycle-icon">&#x2714;</span>
              <span class="evt-label">{{ t('agent.labelTaskDone') }}</span>
              <span class="evt-task-id">{{ evt.metadata?.task_id }}</span>
            </div>
            <div v-else-if="evt.type === 'warning' && evt.content" class="agent-event warning">
              <span class="evt-warning-icon">&#x26A0;</span>
              <span class="evt-content-text">{{ evt.content }}</span>
            </div>
          </template>
          <MarkdownBlock
            v-if="msg.content && msg.role === 'assistant'"
            :source="msg.content"
            :streaming="msg.isStreaming"
            class="agent-bubble agent-markdown"
          />
          <div v-else-if="msg.content" class="agent-bubble">{{ msg.content }}</div>
          <div v-if="msg.isStreaming" class="agent-streaming">
            <span class="dot-wave"><i></i><i></i><i></i></span>
          </div>
        </div>
      </div>
      <!-- Keep a reliable fallback until Monaco confirms that the inline diff is visible. -->
      <AgentApprovalInline
        v-if="showApprovalFallback"
        :pending="pendingApproval"
        @decide="handleApprovalDecision"
      />
      <div class="agent-input-area">
        <div
          class="agent-workspace-bar"
          :class="{ active: !!workspaceName, inactive: !workspaceName }"
        >
          <span class="ws-dot"></span>
          <span class="ws-name" v-if="workspaceName">{{ workspaceName }}</span>
          <span class="ws-name muted" v-else>{{ t('agent.noProject') }}</span>
        </div>
        <div v-if="contextText" class="agent-context-note">
          {{
            t('agent.contextEditor', {
              type: editorSelection.text ? t('agent.contextSelection') : t('agent.contextDocument'),
              count: contextText.length,
            })
          }}
        </div>
        <div
          v-if="selectedSkills.length"
          class="agent-selected-skills"
          :aria-label="t('agent.selectedSkills')"
        >
          <span class="selected-skills-label">{{ t('agent.selectedSkills') }}</span>
          <button
            v-for="skill in selectedSkills"
            :key="skill.name"
            class="selected-skill-chip"
            :title="t('agent.removeSkill')"
            @click="removeSkill(skill.name)"
          >
            <span>{{ skillDisplayName(skill) }}</span
            ><span aria-hidden="true">×</span>
          </button>
        </div>
        <!-- File attachments -->
        <div class="agent-attachments" v-if="files.length">
          <div class="agent-file" v-for="f in files" :key="f.name">
            <svg
              width="12"
              height="12"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
            </svg>
            <span>{{ f.name }}</span>
            <button
              class="agent-file-remove"
              :title="t('agent.removeAttachment')"
              @click="removeFile(f.name)"
            >
              ×
            </button>
          </div>
        </div>
        <div class="agent-composer">
          <AgentSlashMenu
            v-if="slashMenuOpen"
            :items="slashItems"
            :active-index="slashActiveIndex"
            :loading="skillsLoading"
            :menu-label="t('agent.slash.menuLabel')"
            :loading-label="t('agent.slash.loading')"
            :empty-label="t('agent.slash.empty')"
            :preset-label="t('agent.slash.presetGroup')"
            :skill-label="t('agent.slash.skillGroup')"
            :selected-label="t('agent.slash.selected')"
            @hover="slashActiveIndex = $event"
            @select="applySlashCommand"
          />
          <div class="agent-input-row">
            <button
              class="agent-attach-btn"
              @click="attachFile"
              :title="t('agent.addAttachment')"
              :disabled="sending"
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <path
                  d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"
                />
              </svg>
            </button>
            <textarea
              ref="agentInputEl"
              v-model="input"
              rows="2"
              role="combobox"
              aria-autocomplete="list"
              aria-controls="agent-slash-menu"
              :aria-expanded="slashMenuOpen"
              :aria-activedescendant="slashActiveDescendant"
              @keydown="handleInputKeydown"
              :disabled="sending"
              :placeholder="t('agent.inputPlaceholder')"
              class="agent-input"
            ></textarea>
            <button
              v-if="agentSpeech.isSupported"
              class="agent-attach-btn"
              :class="{ 'voice-active': agentSpeech.status.value === 'listening' }"
              :title="
                agentSpeech.status.value === 'listening'
                  ? t('agent.voiceStop')
                  : t('agent.voiceStart')
              "
              :disabled="sending"
              @click="toggleAgentSpeech"
            >
              <Mic :size="14" :stroke-width="2" />
            </button>
            <button
              class="agent-send-btn"
              :class="{ stopping: sending }"
              @click="sending ? abortSession() : handleComposerSubmit()"
              :disabled="!sending && !input.trim()"
              :title="sending ? t('agent.stopGenerate') : t('agent.send')"
            >
              <svg v-if="sending" width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                <rect x="3" y="3" width="18" height="18" rx="3" />
              </svg>
              <svg
                v-else
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Docs Tab -->
    <div
      id="agent-panel-docs"
      v-show="tab === 'docs'"
      role="tabpanel"
      aria-labelledby="agent-tab-docs"
      class="agent-docs"
    >
      <div class="docs-toolbar">
        <span class="docs-title">{{ t('agent.docsTitle') }}</span>
        <span class="docs-subtitle">{{ t('agent.docsSubtitle') }}</span>
        <div class="docs-toolbar-actions">
          <button class="btn primary u-interactive" @click="emit('switch-to-sources')">
            <span>{{ t('agent.openProjectLibrary') }}</span>
          </button>
          <button
            class="btn ghost u-interactive"
            :class="{ refreshing: sourceLibrary.loading.value }"
            @click="fetchDocs"
            :disabled="sourceLibrary.loading.value"
          >
            {{ t('agent.refresh') }}
          </button>
        </div>
      </div>
      <div
        v-if="sourceLibrary.loading.value && sourceLibrary.sources.value.length === 0"
        class="docs-list"
      >
        <div v-for="i in 4" :key="i" class="doc-card skel" :style="{ '--stagger-i': i - 1 }">
          <div class="doc-info" style="flex: 1">
            <UiSkeleton shape="line" height="13" width="70%" />
            <UiSkeleton shape="line" height="10" width="30%" />
          </div>
        </div>
      </div>
      <div v-else-if="sourceLibrary.sources.value.length === 0" class="docs-empty anim-fade-in-up">
        <span class="empty-glyph">▤</span>
        <p>{{ t('agent.noDocs') }}</p>
      </div>
      <TransitionGroup v-else name="v-list-stagger" tag="div" class="docs-list">
        <div
          v-for="(doc, idx) in sourceLibrary.sources.value"
          :key="doc.id"
          class="doc-card u-interactive"
          :style="{ '--stagger-i': idx }"
        >
          <div class="doc-info">
            <span class="doc-title">{{ doc.title || doc.id }}</span>
            <span class="doc-meta">
              {{
                doc.rag_status === 'ready'
                  ? t('agent.projectSourceReady')
                  : t('agent.projectSourceNotIndexed')
              }}
            </span>
          </div>
        </div>
      </TransitionGroup>
    </div>

    <!-- Skills and paper templates -->
    <div
      id="agent-panel-templates"
      v-show="tab === 'templates'"
      role="tabpanel"
      aria-labelledby="agent-tab-templates"
      class="agent-templates"
    >
      <div class="docs-toolbar">
        <div class="skills-heading">
          <span class="docs-title">{{ t('agent.skillsTitle') }}</span>
          <span class="docs-subtitle">{{ t('agent.skillsSubtitle') }}</span>
        </div>
        <button
          class="btn ghost u-interactive"
          :class="{ refreshing: skillsLoading }"
          @click="fetchAgentSkills"
          :disabled="skillsLoading"
        >
          {{ t('agent.refresh') }}
        </button>
      </div>
      <div v-if="skillsLoading && agentSkills.length === 0" class="skills-list">
        <UiSkeleton v-for="i in 5" :key="i" shape="card" height="66" class="tpl-skel" />
      </div>
      <div v-else-if="agentSkills.length === 0" class="docs-empty anim-fade-in-up">
        <span class="empty-glyph">◇</span>
        <p>{{ t('agent.noSkills') }}</p>
      </div>
      <TransitionGroup v-else name="v-list-stagger" tag="div" class="skills-list">
        <div
          v-for="(skill, idx) in visibleAgentSkills"
          :key="skill.name"
          class="skill-row"
          :class="{ selected: isSkillSelected(skill.name) }"
          :style="{ '--stagger-i': idx }"
        >
          <div class="skill-copy">
            <div class="skill-name-row">
              <span class="skill-name">{{ skillDisplayName(skill) }}</span>
              <span v-if="skill.category === 'nature'" class="skill-family">Nature</span>
            </div>
            <span class="skill-description">{{ skillDisplayDescription(skill) }}</span>
          </div>
          <button class="skill-use-btn" @click="useSkill(skill)">
            {{ isSkillSelected(skill.name) ? t('agent.skillSelected') : t('agent.useSkill') }}
          </button>
        </div>
      </TransitionGroup>

      <details class="paper-template-section">
        <summary>{{ t('agent.templatesTitle') }}</summary>
        <div class="template-section-toolbar">
          <span>{{ t('agent.templatesSubtitle') }}</span>
          <button
            class="btn ghost u-interactive"
            :class="{ refreshing: templatesLoading }"
            @click="loadPaperTemplates"
            :disabled="templatesLoading"
          >
            {{ t('agent.refreshTemplates') }}
          </button>
        </div>
        <div v-if="templatesLoading && templates.length === 0" class="template-grid">
          <UiSkeleton v-for="i in 4" :key="i" shape="card" height="58" class="tpl-skel" />
        </div>
        <div v-else-if="templates.length === 0" class="template-empty">
          <span>{{ t('agent.noTemplates') }}</span>
          <button class="btn ghost u-interactive" @click="ingestPaperAssets">
            {{ t('agent.indexTemplates') }}
          </button>
        </div>
        <TransitionGroup v-else name="v-list-stagger" tag="div" class="template-grid">
          <button
            v-for="template in templates"
            :key="template.id"
            class="template-card u-interactive"
            @click="previewingTemplate = template"
          >
            <span class="template-icon">{{ template.icon }}</span>
            <span class="template-info">
              <span class="template-name">{{ template.name }}</span>
              <span class="template-venue">{{ template.venue }}</span>
            </span>
          </button>
        </TransitionGroup>
      </details>
      <Transition name="v-scale-in">
        <div v-if="previewingTemplate" class="template-preview">
          <div class="template-preview-header">
            <span>{{ previewingTemplate.icon }} {{ previewingTemplate.name }}</span>
            <button class="btn ghost u-interactive" @click="previewingTemplate = null">
              &times;
            </button>
          </div>
          <div class="template-preview-desc">{{ previewingTemplate.description }}</div>
          <button
            class="btn primary u-interactive"
            style="margin-top: 8px; width: 100%"
            @click="createFromTemplate(previewingTemplate)"
          >
            {{ t('agent.createFromThisTemplate') }}
          </button>
        </div>
      </Transition>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, defineAsyncComponent, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'

const { t, te } = useI18n()

import { useAgentChat } from '../composables/useAgentChat'
import { useEditor } from '../composables/useEditor'
import { useEditorState } from '../composables/useEditorState'
import { useFileTree } from '../composables/useFileTree'
import { useSourceLibrary } from '../composables/useSourceLibrary'
import AgentApprovalInline from './AgentApprovalInline.vue'
import AgentExecutionGroup from './AgentExecutionGroup.vue'
import AgentThoughtGroup from './AgentThoughtGroup.vue'
import AgentSlashMenu from './AgentSlashMenu.vue'
import AgentSessionList from './AgentSessionList.vue'
import { Pin, PinOff, Mic, Plus } from './ui/icons'
import { API_BASE } from '../utils/api'
import type { AgentSessionInfo, AgentSkill } from '../types'
import { useSpeechRecognition } from '../composables/useSpeechRecognition'
import UiSkeleton from './ui/UiSkeleton.vue'
import { useToast } from '../composables/useToast'
import { getCurrentWindow } from '@tauri-apps/api/window'
import { open as openDialog } from '@tauri-apps/plugin-dialog'
import {
  filterAgentSlashCommands,
  parseAgentSlashInvocation,
  skillSlashCommand,
  type AgentSlashCommand,
} from '../composables/useAgentSlashCommands'

// Keep the Markdown parser/sanitizer and KaTeX outside the initial Agent shell.
// Each block recomputes only when its own message content changes.
const MarkdownBlock = defineAsyncComponent(() => import('./MarkdownBlock.vue'))

let voiceBaseInput = ''
const agentSpeech = useSpeechRecognition({
  onResult: (text) => {
    input.value = voiceBaseInput + (voiceBaseInput ? ' ' : '') + text
  },
  onEnd: () => {
    voiceBaseInput = ''
  },
})

function toggleAgentSpeech() {
  if (agentSpeech.status.value === 'listening') {
    voiceBaseInput = ''
    agentSpeech.stop()
    agentInputEl.value?.focus()
  } else {
    voiceBaseInput = input.value
    agentSpeech.start()
  }
}

// Tauri is available when window.__TAURI_INTERNALS__ exists
const _isTauri = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window

const props = defineProps<{
  open: boolean
  standalone?: boolean
  embedded?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
  (e: 'switch-to-editor'): void
  (e: 'switch-to-sources'): void
}>()

// ── Floating panel: native OS window (Tauri) or in-app overlay (web) ─────────

const isStandalone = computed(() => props.standalone === true)
const isEmbedded = computed(() => props.embedded === true)
const panelInactive = computed(() => !props.open && !isFloating.value && !isStandalone.value)

// In-app float fallback (web mode only)
const isFloating = ref(false)
const floatX = ref(0)
const floatY = ref(0)
let _dragActive = false
let _dragOffX = 0
let _dragOffY = 0

// Tauri native OS window ref
let _agentWindow: import('@tauri-apps/api/webviewWindow').WebviewWindow | null = null

async function openAgentWindow() {
  const { WebviewWindow } = await import('@tauri-apps/api/webviewWindow')

  // Close any existing agent window first
  try {
    const old = await WebviewWindow.getByLabel('agent')
    if (old) await old.close()
  } catch {
    /* Window may already be gone. */
  }

  // Pass agent-only flag and optional session via URL params — sessionStorage is
  // window-isolated in Tauri so URL params are the only reliable cross-window channel.
  const params = new URLSearchParams({ 'agent-only': '1' })
  const { sessionId } = useAgentChat()
  if (sessionId.value) params.set('session', sessionId.value)
  const url = `${window.location.origin}/?${params}`

  _agentWindow = new WebviewWindow('agent', {
    url,
    title: t('agent.title'),
    width: 400,
    height: 560,
    minWidth: 320,
    minHeight: 400,
    resizable: true,
    decorations: false,
    shadow: true,
    center: true,
    visible: true,
    skipTaskbar: false,
    alwaysOnTop: true,
  })

  await new Promise<void>((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error('window timeout')), 5000)
    _agentWindow!.once('tauri://created', () => {
      clearTimeout(timeout)
      resolve()
    })
    _agentWindow!.once('tauri://error', (e) => {
      clearTimeout(timeout)
      reject(new Error(String(e)))
    })
  })

  _agentWindow.once('tauri://destroyed', () => {
    _agentWindow = null
    emit('update:open', true)
  })

  emit('update:open', false)
}

async function closeAgentWindow() {
  try {
    const { WebviewWindow } = await import('@tauri-apps/api/webviewWindow')
    const w = await WebviewWindow.getByLabel('agent')
    if (w) await w.close()
  } catch {
    /* Non-Tauri/browser preview. */
  }
  _agentWindow = null
  emit('update:open', true)
}

async function toggleFloat() {
  if (_isTauri) {
    // Desktop: use real OS window so it can move outside app bounds
    if (_agentWindow) {
      await closeAgentWindow()
    } else {
      try {
        await openAgentWindow()
      } catch (err) {
        console.error('Failed to open agent window:', err)
        _agentWindow = null
        // Tauri failed — fall through to in-app float
        _openInAppFloat()
      }
    }
  } else {
    // Browser: in-app draggable overlay
    if (isFloating.value) {
      isFloating.value = false
      emit('update:open', true)
    } else {
      _openInAppFloat()
    }
  }
}

function _openInAppFloat() {
  floatX.value = Math.max(0, window.innerWidth - 440)
  floatY.value = 80
  isFloating.value = true
}

// In-app drag (web fallback only)
function onHeaderMouseDown(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (target.closest('button')) return
  if (!isFloating.value) return
  _dragActive = true
  _dragOffX = e.clientX - floatX.value
  _dragOffY = e.clientY - floatY.value
  window.addEventListener('mousemove', _onDragMove)
  window.addEventListener('mouseup', _onDragUp, { once: true })
  e.preventDefault()
}

function _onDragMove(e: MouseEvent) {
  if (!_dragActive) return
  floatX.value = Math.max(0, Math.min(e.clientX - _dragOffX, window.innerWidth - 380))
  floatY.value = Math.max(0, Math.min(e.clientY - _dragOffY, window.innerHeight - 100))
}

function _onDragUp() {
  _dragActive = false
  window.removeEventListener('mousemove', _onDragMove)
}

// Standalone window: drag via Tauri OS-level API
function onHeaderMouseDown_standalone(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (target.closest('button')) return
  getCurrentWindow().startDragging()
}

function _headerMouseDown(e: MouseEvent) {
  if (isStandalone.value) {
    onHeaderMouseDown_standalone(e)
  } else {
    onHeaderMouseDown(e)
  }
}

// Standalone: dock back to main window
async function onDockBack() {
  localStorage.setItem('agent-dock-back', Date.now().toString())
  await getCurrentWindow().close()
}

let _unlistenStorage: (() => void) | null = null

onMounted(async () => {
  if (isStandalone.value) {
    // Read session from URL params (passed by openAgentWindow)
    const params = new URLSearchParams(window.location.search)
    const sid = params.get('session')
    if (sid) await loadWorkflowMessages(sid)
  } else {
    // Listen for dock-back signal from standalone window
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
  messages,
  sending,
  pendingApproval,
  agentSkills,
  skillsLoading,
  sendMessage: agentSendMessage,
  sendApproval,
  abortSession,
  startNewWorkflow,
  loadWorkflowMessages,
  sessionId,
  pendingCheckpoint,
  fetchSessions: _fetchSessions,
  fetchAgentSkills,
} = useAgentChat()

const {
  selection: editorSelection,
  content: editorContent,
  activeTab: editorActiveTab,
  reloadOpenTabs,
  applyExternalFileUpdate,
} = useEditor()

const {
  tabs: editorTabs,
  inlineDiffVisible,
  setActiveEdit,
  clearActiveEdit,
  shouldShowApprovalFallback,
  shouldShowInlineDiff,
} = useEditorState()

const { rootDir, refresh: refreshFileTree } = useFileTree()
const sourceLibrary = useSourceLibrary()

const workspaceName = computed(() => {
  if (!rootDir.value) return null
  return rootDir.value.split(/[\\/]/).filter(Boolean).pop() || rootDir.value
})

const tab = ref<'chat' | 'docs' | 'templates' | 'sessions'>('chat')
type AgentTab = typeof tab.value
const AGENT_TABS: AgentTab[] = ['chat', 'docs', 'templates', 'sessions']
const input = ref('')
const agentInputEl = ref<HTMLTextAreaElement | null>(null)
const messagesRef = ref<HTMLElement | null>(null)
const sessionListRef = ref<InstanceType<typeof AgentSessionList> | null>(null)
// 自动滚动：用户未手动上滚时保持跟底
const _userScrolledUp = ref(false)
let _focusBeforeOpen: HTMLElement | null = null

function selectTab(nextTab: AgentTab) {
  tab.value = nextTab
  if (nextTab === 'sessions') refreshSessions()
}

function onTabKeydown(event: KeyboardEvent) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  const currentIndex = AGENT_TABS.indexOf(tab.value)
  const nextIndex =
    event.key === 'Home'
      ? 0
      : event.key === 'End'
        ? AGENT_TABS.length - 1
        : (currentIndex + (event.key === 'ArrowRight' ? 1 : -1) + AGENT_TABS.length) %
          AGENT_TABS.length
  selectTab(AGENT_TABS[nextIndex])
  nextTick(() => document.getElementById(`agent-tab-${AGENT_TABS[nextIndex]}`)?.focus())
}

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
const files = ref<{ name: string; path: string }[]>([])
const selectedSkillNames = ref<string[]>([])
const slashActiveIndex = ref(0)
const slashDismissed = ref(false)
const { warn: showWarning } = useToast()

const visibleAgentSkills = computed(() =>
  [...agentSkills.value].sort((a, b) => {
    if (a.category === b.category) return skillDisplayName(a).localeCompare(skillDisplayName(b))
    return a.category === 'nature' ? -1 : 1
  }),
)

const selectedSkills = computed(() =>
  selectedSkillNames.value
    .map((name) => agentSkills.value.find((skill) => skill.name === name))
    .filter((skill): skill is AgentSkill => Boolean(skill)),
)

function skillDisplayName(skill: AgentSkill): string {
  const key = `agent.skills.${skill.name}.name`
  return te(key) ? t(key) : skill.name.replaceAll('_', ' ')
}

function skillDisplayDescription(skill: AgentSkill): string {
  const key = `agent.skills.${skill.name}.description`
  return te(key) ? t(key) : skill.description
}

function skillPromptText(skill: AgentSkill): string {
  const promptKey = `agent.skills.${skill.name}.prompt`
  return te(promptKey)
    ? t(promptKey)
    : t('agent.skillPromptFallback', { skill: skillDisplayName(skill) })
}

const slashPresetItems = computed<AgentSlashCommand[]>(() => [
  {
    id: 'preset-polish',
    command: '/polish',
    kind: 'preset',
    label: t('agent.slash.presets.polish.label'),
    description: t('agent.slash.presets.polish.description'),
    prompt: t('agent.slash.presets.polish.prompt'),
  },
  {
    id: 'preset-review',
    command: '/review',
    kind: 'preset',
    label: t('agent.slash.presets.review.label'),
    description: t('agent.slash.presets.review.description'),
    prompt: t('agent.slash.presets.review.prompt'),
  },
  {
    id: 'preset-outline',
    command: '/outline',
    kind: 'preset',
    label: t('agent.slash.presets.outline.label'),
    description: t('agent.slash.presets.outline.description'),
    prompt: t('agent.slash.presets.outline.prompt'),
  },
  {
    id: 'preset-cite',
    command: '/cite',
    kind: 'preset',
    label: t('agent.slash.presets.cite.label'),
    description: t('agent.slash.presets.cite.description'),
    prompt: t('agent.slash.presets.cite.prompt'),
  },
  {
    id: 'preset-research',
    command: '/research',
    kind: 'preset',
    label: t('agent.slash.presets.research.label'),
    description: t('agent.slash.presets.research.description'),
    prompt: t('agent.slash.presets.research.prompt'),
  },
  {
    id: 'preset-translate',
    command: '/translate',
    kind: 'preset',
    label: t('agent.slash.presets.translate.label'),
    description: t('agent.slash.presets.translate.description'),
    prompt: t('agent.slash.presets.translate.prompt'),
  },
])

const slashSkillItems = computed<AgentSlashCommand[]>(() =>
  visibleAgentSkills.value.map((skill) => ({
    id: `skill-${skill.name.replaceAll(/[^a-zA-Z0-9_-]/g, '-')}`,
    command: skillSlashCommand(skill),
    kind: 'skill',
    label: skillDisplayName(skill),
    description: skillDisplayDescription(skill),
    prompt: skillPromptText(skill),
    skillName: skill.name,
    selected: isSkillSelected(skill.name),
  })),
)

const slashCommands = computed(() => [...slashPresetItems.value, ...slashSkillItems.value])
const slashMatch = computed(() => input.value.match(/^\/([^\s]*)$/))
const slashMenuOpen = computed(
  () => Boolean(slashMatch.value) && !sending.value && !slashDismissed.value,
)
const slashQuery = computed(() => slashMatch.value?.[1] || '')
const slashItems = computed(() =>
  filterAgentSlashCommands(slashCommands.value, slashQuery.value, 10),
)
const slashActiveDescendant = computed(() => {
  const active = slashItems.value[slashActiveIndex.value]
  return slashMenuOpen.value && active ? `agent-slash-${active.id}` : undefined
})

function isSkillSelected(name: string): boolean {
  return selectedSkillNames.value.includes(name)
}

async function useSkill(skill: AgentSkill) {
  selectedSkillNames.value = [skill.name]
  if (!input.value.trim()) input.value = skillPromptText(skill)
  tab.value = 'chat'
  await nextTick()
  agentInputEl.value?.focus()
}

function removeSkill(name: string) {
  selectedSkillNames.value = selectedSkillNames.value.filter((skillName) => skillName !== name)
}

async function applySlashCommand(item: AgentSlashCommand, argument = '') {
  selectedSkillNames.value = item.skillName ? [item.skillName] : []
  input.value = [item.prompt, argument].filter(Boolean).join('\n\n')
  slashActiveIndex.value = 0
  await nextTick()
  agentInputEl.value?.focus()
}

function moveSlashSelection(offset: number) {
  const count = slashItems.value.length
  if (!count) return
  slashActiveIndex.value = (slashActiveIndex.value + offset + count) % count
}

function handleInputKeydown(event: KeyboardEvent) {
  if (event.isComposing) return
  if (slashMenuOpen.value) {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      moveSlashSelection(event.key === 'ArrowDown' ? 1 : -1)
      return
    }
    if (event.key === 'Home' || event.key === 'End') {
      event.preventDefault()
      slashActiveIndex.value = event.key === 'Home' ? 0 : Math.max(0, slashItems.value.length - 1)
      return
    }
    if (event.key === 'Escape') {
      event.preventDefault()
      slashDismissed.value = true
      return
    }
    if (
      (event.key === 'Enter' || event.key === 'Tab') &&
      !event.shiftKey &&
      !event.altKey &&
      !event.ctrlKey &&
      !event.metaKey &&
      slashItems.value.length
    ) {
      event.preventDefault()
      void applySlashCommand(slashItems.value[slashActiveIndex.value])
      return
    }
  }
  if (
    event.key === 'Enter' &&
    !event.shiftKey &&
    !event.altKey &&
    !event.ctrlKey &&
    !event.metaKey
  ) {
    event.preventDefault()
    void sendMessage()
  }
}

function handleComposerSubmit() {
  if (slashMenuOpen.value && slashItems.value.length) {
    void applySlashCommand(slashItems.value[slashActiveIndex.value])
    return
  }
  void sendMessage()
}

const contextText = computed(() => {
  if (!editorActiveTab.value) return ''
  return editorSelection.value.text || editorContent.value
})

// ── Current status from streaming events ──
const currentStatus = computed(() => {
  const streaming = messages.value.find((m) => m.isStreaming)
  if (!streaming) return ''
  if (pendingApproval.value)
    return t('agent.awaitingApproval', { tool: pendingApproval.value.tool_name })
  for (let i = streaming.events.length - 1; i >= 0; i--) {
    const evt = streaming.events[i]
    if (evt.type === 'thinking' || evt.type === 'thought') return t('agent.thinkingCompact')
    if (evt.type === 'tool_call') return t('agent.execution.running', { count: 1 })
    if (evt.type === 'tool_result') return t('agent.execution.completed', { count: 1 })
    if (evt.type === 'task_started') return t('agent.labelTask')
    if (evt.type === 'task_done') return t('agent.labelTaskDone')
    if (evt.type === 'warning') return evt.content
  }
  return ''
})

// ── Approval ──
const showInlineDiff = computed(() => {
  const p = pendingApproval.value
  if (!p) return false
  return shouldShowInlineDiff(p.tool_name, p.args || {}, editorTabs.value, p.preview)
})

const showApprovalFallback = computed(() =>
  shouldShowApprovalFallback(Boolean(pendingApproval.value), inlineDiffVisible.value),
)

async function handleApprovalDecision(decision: 'allow_once' | 'allow_session' | 'deny') {
  const pending = pendingApproval.value
  if (!pending) return
  await sendApproval(pending.event_id, decision)
}

// Route file-edit approvals to inline diff editor overlay
watch(pendingApproval, (p) => {
  if (p && showInlineDiff.value) {
    const preview = p.preview as Record<string, unknown> | undefined
    const args = p.args as Record<string, unknown> | undefined
    setActiveEdit({
      editId: p.event_id,
      eventId: p.event_id,
      sessionId: sessionId.value || '',
      operation: (p.tool_name === 'write_file' ? 'write_file' : 'str_replace') as
        'str_replace' | 'write_file',
      filePath: (args?.file_path as string) || '',
      oldText: (preview?.old_text as string) ?? (args?.old_string as string) ?? '',
      newText:
        (preview?.new_text as string) ??
        (args?.new_string as string) ??
        (args?.content as string) ??
        '',
    })
  } else {
    clearActiveEdit()
  }
})

// Agent 写入文件后实时刷新文件树和编辑器
watch(pendingCheckpoint, () => {
  const cp = pendingCheckpoint.value
  if (cp) {
    const filePath = cp.file as string | undefined
    const content = cp.content as string | undefined
    if (filePath && content && !cp.content_truncated) {
      const result = applyExternalFileUpdate(filePath, content)
      if (result === 'conflict') {
        const name = filePath.split(/[\\/]/).pop() || filePath
        showWarning(t('agent.unsavedFileConflict', { name }), 8000)
      }
    }
    refreshFileTree()
    reloadOpenTabs()
  }
})

// ── Sessions ──
async function refreshSessions() {
  sessions.value = await _fetchSessions()
  sessionListRef.value?.fetchSessions()
}

async function handleSessionOpen(session: AgentSessionInfo) {
  const loaded = await loadWorkflowMessages(session.id)
  if (!loaded) {
    showWarning(t('agent.sessionLoadFailed'), 6000)
    return
  }
  tab.value = 'chat'
  _userScrolledUp.value = false
  await nextTick()
  _scrollToBottom()
}

function handleNewSession() {
  if (sending.value || pendingApproval.value) return
  startNewWorkflow()
  input.value = ''
  files.value = []
  selectedSkillNames.value = []
  _userScrolledUp.value = false
  nextTick(() => agentInputEl.value?.focus())
}

// ── Send message ──
async function sendMessage() {
  let text = input.value.trim()
  if (!text || sending.value) return
  const invocation = parseAgentSlashInvocation(text)
  if (invocation) {
    const item = slashCommands.value.find((candidate) => candidate.command === invocation.command)
    if (item) {
      selectedSkillNames.value = item.skillName ? [item.skillName] : []
      text = [item.prompt, invocation.argument].filter(Boolean).join('\n\n')
    }
  }
  input.value = ''

  // Pass file paths to agent — let it read with read_file tool
  let fullMsg = text
  if (files.value.length) {
    const pathList = files.value.map((f) => `- ${f.path}`).join('\n')
    fullMsg = `${text}\n\n[${t('agent.attachedFilesHint')}\n${pathList}]`
    files.value = []
  }

  await agentSendMessage(
    fullMsg,
    contextText.value,
    '',
    rootDir.value || undefined,
    editorActiveTab.value?.path || undefined,
    selectedSkillNames.value,
    editorSelection.value.text && editorActiveTab.value?.path
      ? {
          selection: {
            filePath: editorActiveTab.value.path,
            startLine: editorSelection.value.startLine,
            startColumn: editorSelection.value.startCol,
            endLine: editorSelection.value.endLine,
            endColumn: editorSelection.value.endCol,
            text: editorSelection.value.text,
          },
        }
      : undefined,
  )
  refreshFileTree()
  reloadOpenTabs()
  await nextTick()
  _scrollToBottom()
}

// ── File operations ─────────────────────────────────────────
async function attachFile() {
  try {
    const selected = await openDialog({
      multiple: true,
      filters: [
        {
          name: 'Text',
          extensions: [
            'md',
            'txt',
            'tex',
            'py',
            'js',
            'ts',
            'json',
            'yaml',
            'yml',
            'xml',
            'html',
            'css',
            'csv',
            'pdf',
          ],
        },
      ],
    })
    if (!selected) return
    const paths = (Array.isArray(selected) ? selected : [selected]) as string[]
    for (const p of paths) {
      const name = p.split(/[\\/]/).pop() || p
      if (files.value.some((f) => f.name === name)) continue
      files.value.push({ name, path: p })
    }
  } catch {
    /* dialog not available */
  }
}

function removeFile(name: string) {
  files.value = files.value.filter((f) => f.name !== name)
}

async function fetchDocs() {
  if (!rootDir.value) return
  await sourceLibrary.loadSources().catch(() => undefined)
}

// ── Paper templates ──
interface PaperTemplate {
  id: string
  name: string
  venue: string
  description: string
  icon: string
}
const templates = ref<PaperTemplate[]>([])
const templatesLoading = ref(false)
const previewingTemplate = ref<PaperTemplate | null>(null)

async function loadPaperTemplates() {
  templatesLoading.value = true
  try {
    const resp = await fetch(`${API_BASE}/api/paper-assets/templates`)
    if (resp.ok) {
      const data = await resp.json()
      templates.value = data.templates || []
    }
  } catch (e) {
    console.warn('loadPaperTemplates failed:', e)
  } finally {
    templatesLoading.value = false
  }
}

async function ingestPaperAssets() {
  try {
    await fetch(`${API_BASE}/api/paper-assets/ingest`, { method: 'POST' })
    loadPaperTemplates()
  } catch (e) {
    console.warn('ingestPaperAssets failed:', e)
  }
}

function createFromTemplate(t: PaperTemplate) {
  tab.value = 'chat'
  fetch(`${API_BASE}/api/paper-scaffold`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ template_id: t.id, title: '' }),
  })
    .then((r) => r.json())
    .then((data) => {
      if (data.markdown) {
        window.dispatchEvent(
          new CustomEvent('paper-scaffold', {
            detail: { markdown: data.markdown, templateId: t.id },
          }),
        )
      }
    })
    .catch(() => {})
  previewingTemplate.value = null
}

// ── Watchers ──
watch(
  () => props.open,
  async (isOpen) => {
    if (isOpen) {
      if (!_focusBeforeOpen) _focusBeforeOpen = document.activeElement as HTMLElement | null
      await Promise.all([fetchDocs(), fetchAgentSkills()])
      await nextTick()
      if (tab.value === 'chat') agentInputEl.value?.focus()
    } else if (!isFloating.value && !isStandalone.value) {
      _focusBeforeOpen?.focus()
      _focusBeforeOpen = null
    }
  },
)

watch(input, () => {
  slashDismissed.value = false
  slashActiveIndex.value = 0
})

watch(slashActiveDescendant, async (id) => {
  if (!id) return
  await nextTick()
  document.getElementById(id)?.scrollIntoView({ block: 'nearest' })
})

watch(slashMenuOpen, (isOpen) => {
  if (isOpen && agentSkills.value.length === 0 && !skillsLoading.value) {
    void fetchAgentSkills()
  }
})

watch(tab, (t) => {
  if (t === 'templates') {
    if (templates.value.length === 0) loadPaperTemplates()
    if (agentSkills.value.length === 0) fetchAgentSkills()
  }
})

// Track only the fields that can change the rendered message height. This
// avoids recursively traversing every historical Agent event on each token.
const messageRenderSignal = computed(() => {
  const lastMessage = messages.value[messages.value.length - 1]
  if (!lastMessage) return '0'
  return `${messages.value.length}:${lastMessage.id}:${lastMessage.content.length}:${lastMessage.events.length}:${lastMessage.isStreaming ? 1 : 0}`
})

// 流式输出自动跟底：若用户没有手动上滚则自动滚底
watch(messageRenderSignal, async () => {
  if (_userScrolledUp.value) return
  await nextTick()
  _scrollToBottom()
})

// 发送新消息时强制重置到底部（无论用户之前是否上滚）
watch(sending, (nowSending) => {
  if (nowSending) {
    _userScrolledUp.value = false
    nextTick(() => _scrollToBottom())
  }
})

// 审批弹出时停止自动滚底 — 让用户看清 tool_call 上下文
watch(pendingApproval, (val) => {
  if (val) _userScrolledUp.value = true
})

onUnmounted(() => {
  window.removeEventListener('mousemove', _onDragMove)
  window.removeEventListener('mouseup', _onDragUp)
  _unlistenStorage?.()
  _unlistenStorage = null
})
</script>

<style scoped>
.agent-panel {
  position: fixed;
  top: 0;
  right: 0;
  width: min(420px, 100vw);
  height: calc(100vh - 62px);
  margin-top: 62px;
  background: var(--c-glass);
  border-left: none;
  box-shadow:
    -20px 0 80px rgba(0, 0, 0, 0.4),
    inset 1px 0 0 rgba(255, 255, 255, 0.05);
  backdrop-filter: blur(32px);
  -webkit-backdrop-filter: blur(32px);
  display: flex;
  flex-direction: column;
  z-index: 200;
  transform: translateX(100%);
  transition: transform var(--motion-page, 320ms) var(--ease-spring);
}
.agent-panel.open {
  transform: translateX(0);
}

/* Standalone mode: rounded floating panel look */
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

/* In-app floating mode: draggable overlay */
.agent-panel.floating {
  right: auto;
  top: auto;
  width: 400px;
  height: 560px;
  margin-top: 0;
  transform: none !important;
  border-radius: var(--radius-xl);
  border: 1px solid var(--c-glass-border);
  box-shadow:
    0 24px 80px rgba(0, 0, 0, 0.5),
    0 0 0 1px rgba(255, 255, 255, 0.06);
  overflow: hidden;
  z-index: 500;
}
.agent-panel.embedded {
  position: relative;
  top: auto;
  right: auto;
  width: 0;
  height: 100%;
  margin-top: 0;
  flex: 0 0 auto;
  transform: none;
  border-left: 0;
  box-shadow: none;
  overflow: hidden;
  visibility: hidden;
  transition:
    width var(--motion-page) var(--ease-out),
    visibility 0s linear var(--motion-page);
}
.agent-panel.embedded.open {
  width: min(420px, 38vw);
  border-left: 1px solid var(--c-border);
  visibility: visible;
  transition:
    width var(--motion-page) var(--ease-out),
    visibility 0s;
}
.agent-panel.embedded .agent-header {
  padding-right: 16px;
}
.agent-header.draggable {
  cursor: grab;
  user-select: none;
}
.agent-header.draggable:active {
  cursor: grabbing;
}

.agent-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 16px 20px 12px;
  border-bottom: none;
  background: linear-gradient(to bottom, var(--c-surface-1) 0%, transparent 100%);
  flex-shrink: 0;
}

.agent-tabs {
  display: flex;
  gap: 4px;
  flex: 1;
  background: var(--c-surface-2);
  padding: 4px;
  border-radius: 12px;
}
.agent-tab {
  padding: 6px 14px;
  border: none;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  background: transparent;
  color: var(--c-text-2);
  transition: all var(--motion-fast);
  white-space: nowrap;
}
.agent-tab:hover {
  color: var(--c-text-0);
}
.agent-tab.active {
  background: var(--c-surface-3);
  color: var(--c-text-0);
  box-shadow:
    0 2px 8px rgba(0, 0, 0, 0.2),
    inset 0 1px 0 rgba(255, 255, 255, 0.08);
}

.agent-header-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}

.agent-hdr-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  background: none;
  border: none;
  color: var(--c-text-3);
  cursor: pointer;
  border-radius: 4px;
  transition: all var(--motion-fast);
}
.agent-hdr-btn:hover {
  color: var(--c-text-0);
  background: var(--c-surface-2);
}
.agent-hdr-btn:disabled,
.agent-hdr-btn:disabled:hover {
  color: var(--c-text-3);
  opacity: 0.45;
  cursor: not-allowed;
  background: transparent;
}

.agent-close-btn {
  background: none;
  border: none;
  color: var(--c-text-3);
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  transition: all var(--motion-fast);
}
.agent-close-btn:hover {
  color: var(--c-text-0);
  background: var(--c-surface-2);
}

.agent-chat {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: linear-gradient(to bottom, transparent, rgba(0, 0, 0, 0.1));
}
.agent-messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px 20px;
  display: flex;
  flex-direction: column;
  gap: 24px;
}
.agent-empty {
  text-align: center;
  color: var(--c-text-3);
  padding: 40px 20px;
}
.agent-empty p:first-child {
  font-family: var(--font-serif);
  font-style: italic;
  font-size: 15px;
  color: var(--c-text-2);
}
.agent-empty .hint {
  font-size: 12px;
}

.agent-msg {
  max-width: 92%;
}
.agent-msg.user {
  align-self: flex-end;
}
.agent-msg.assistant {
  align-self: flex-start;
  max-width: 100%;
}

.agent-bubble {
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
.agent-msg.user .agent-bubble {
  background: var(--c-accent);
  color: #fff;
  border-radius: 16px 16px 4px 16px;
  padding: 12px 18px;
  box-shadow: 0 8px 24px var(--accent-glow);
}
.agent-msg.assistant .agent-bubble {
  background: transparent;
  color: var(--c-text-0);
  padding: 4px 8px;
  border-radius: 0;
  font-size: 14.5px;
  line-height: 1.7;
}

/* Event stream — ink-styled cards */
.agent-event {
  font-size: 12px;
  padding: 8px 12px;
  margin-bottom: 8px;
  border-radius: 10px;
  background: var(--c-surface-2);
  border: 1px solid var(--c-surface-3);
  backdrop-filter: blur(8px);
  box-shadow: 0 4px 12px var(--c-shadow);
  position: relative;
  animation: evt-fade-in var(--motion-base) var(--ease-out);
}
@keyframes evt-fade-in {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
.agent-event.tool-call {
  border-left: 2px solid #3b82f6;
  background: color-mix(in srgb, #3b82f6 6%, var(--c-surface-1));
  animation: evt-slide-in-left 240ms var(--ease-out);
}
@keyframes evt-slide-in-left {
  from {
    opacity: 0;
    transform: translateX(-16px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}
.agent-event.tool-result {
  border-left: 2px solid var(--c-success);
  background: color-mix(in srgb, var(--c-success) 6%, var(--c-surface-1));
  animation: evt-scale-in 240ms var(--ease-spring);
}
@keyframes evt-scale-in {
  from {
    opacity: 0;
    transform: scale(0.96);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}
.agent-event.tool-result.evt-error {
  border-left: 2px solid var(--vermilion-0);
  background: color-mix(in srgb, var(--vermilion-0) 6%, var(--c-surface-1));
  animation: evt-shake 300ms var(--ease-out);
}
@keyframes evt-shake {
  0%,
  100% {
    transform: translateX(0);
  }
  20% {
    transform: translateX(-3px);
  }
  40% {
    transform: translateX(3px);
  }
  60% {
    transform: translateX(-1px);
  }
}

.evt-label {
  font-weight: 600;
  font-size: 11px;
  text-transform: uppercase;
  color: var(--c-text-2);
  flex-shrink: 0;
}
.evt-content-text {
  color: var(--c-text-2);
}
.evt-tool-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}
.evt-tool-icon {
  font-size: 13px;
  flex-shrink: 0;
}
.evt-tool-icon.success {
  color: var(--c-success);
}
.evt-tool-icon.error {
  color: var(--c-danger);
}
.evt-tool-name {
  font-weight: 600;
  color: var(--c-accent);
  font-size: 13px;
}
.evt-tool-desc {
  font-size: 11px;
  color: var(--c-text-2);
  margin: 2px 0 5px 22px;
}
.evt-tool-args {
  background: var(--c-surface-2);
  border-radius: 4px;
  padding: 5px 8px;
  margin-top: 4px;
  border: 1px solid var(--c-surface-3);
}
.evt-args-label {
  font-size: 10px;
  color: var(--c-text-3);
  text-transform: uppercase;
  font-weight: 600;
  margin-right: 6px;
}
.evt-args-code {
  font-size: 11px;
  color: var(--c-text-2);
  white-space: pre-wrap;
  word-break: break-all;
}
.evt-result-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}
.evt-result-tool {
  font-weight: 600;
  color: var(--c-text-2);
  font-size: 12px;
}
.evt-duration {
  font-size: 11px;
  color: var(--c-text-3);
  margin-left: auto;
}
.evt-result-preview {
  font-size: 11px;
  color: var(--c-text-2);
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 80px;
  overflow: hidden;
}

/* Task lifecycle */
.agent-event.task-lifecycle {
  display: flex;
  align-items: center;
  gap: 6px;
  border-left: 2px solid var(--c-accent);
  background: color-mix(in srgb, var(--c-accent) 6%, var(--c-surface-1));
}
.agent-event.task-lifecycle.done {
  border-left-color: var(--c-success);
  background: color-mix(in srgb, var(--c-success) 6%, var(--c-surface-1));
}
.evt-lifecycle-icon {
  font-size: 14px;
  flex-shrink: 0;
}
.evt-task-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--c-text-0);
}
.evt-task-id {
  font-size: 11px;
  color: var(--c-text-3);
  font-family: monospace;
}
.evt-task-progress {
  font-size: 11px;
  color: var(--c-accent-hover);
  margin-left: auto;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
}

/* Risk badge */
.evt-risk-badge {
  font-size: 9px;
  text-transform: uppercase;
  font-weight: 600;
  padding: 1px 5px;
  border-radius: 3px;
}
.evt-risk-badge.risk-safe {
  background: rgba(74, 222, 128, 0.15);
  color: var(--c-success);
}
.evt-risk-badge.risk-moderate {
  background: rgba(245, 158, 11, 0.15);
  color: var(--c-warn);
}
.evt-risk-badge.risk-destructive {
  background: rgba(248, 113, 113, 0.15);
  color: var(--c-danger);
}
.evt-risk-badge.risk-banned {
  background: var(--c-surface-0);
  color: var(--c-danger);
}

/* Warning */
.agent-event.warning {
  display: flex;
  align-items: center;
  gap: 8px;
  border-left: 2px solid var(--c-warn);
  background: color-mix(in srgb, var(--c-warn) 6%, var(--c-surface-1));
}
.evt-warning-icon {
  font-size: 14px;
  flex-shrink: 0;
  color: var(--c-warn);
}

.agent-sessions {
  flex: 1;
  overflow-y: auto;
  padding: 0;
}

/* Thinking progress bar — scanning gradient across the top of the chat area */
.agent-thinking-bar {
  height: 2px;
  flex-shrink: 0;
  background: linear-gradient(
    90deg,
    transparent 0%,
    var(--c-accent) 45%,
    color-mix(in srgb, var(--c-accent) 50%, transparent) 60%,
    transparent 100%
  );
  background-size: 40% 100%;
  background-repeat: no-repeat;
  animation: thinking-scan 1.4s ease-in-out infinite;
}
@keyframes thinking-scan {
  0% {
    background-position: -40% 0;
  }
  100% {
    background-position: 140% 0;
  }
}

.agent-status-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  margin-bottom: 8px;
  background: color-mix(in srgb, var(--c-accent) 12%, var(--c-surface-1));
  border: 1px solid color-mix(in srgb, var(--c-accent) 30%, transparent);
  border-radius: 20px;
  width: fit-content;
  max-width: 100%;
  position: relative;
  overflow: hidden;
}
.agent-status-bar::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(255, 255, 255, 0.07) 50%,
    transparent 100%
  );
  background-size: 200% 100%;
  animation: shimmer-sweep 2s linear infinite;
  pointer-events: none;
}
@keyframes shimmer-sweep {
  0% {
    background-position: -200% 0;
  }
  100% {
    background-position: 200% 0;
  }
}
.agent-status-text {
  font-size: 12px;
  color: var(--c-text-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 260px;
}

/* Three-dot wave — status bar */
.status-dots {
  display: flex;
  gap: 3px;
  align-items: center;
  flex-shrink: 0;
}
.status-dots i {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--c-accent);
  display: block;
  animation: wave-bounce 1.1s ease-in-out infinite;
}
.status-dots i:nth-child(2) {
  animation-delay: 0.15s;
}
.status-dots i:nth-child(3) {
  animation-delay: 0.3s;
}

/* Three-dot wave — streaming indicator */
.agent-streaming {
  display: flex;
  padding: 8px 14px;
}
.dot-wave {
  display: flex;
  gap: 5px;
  align-items: center;
}
.dot-wave i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--c-accent);
  display: block;
  animation: wave-bounce 1.1s ease-in-out infinite;
}
.dot-wave i:nth-child(2) {
  animation-delay: 0.18s;
}
.dot-wave i:nth-child(3) {
  animation-delay: 0.36s;
}
@keyframes wave-bounce {
  0%,
  60%,
  100% {
    transform: translateY(0);
    opacity: 0.25;
  }
  30% {
    transform: translateY(-6px);
    opacity: 1;
  }
}

/* Input area — suspended inkstone */
.agent-input-area {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 16px 20px 24px;
  border-top: none;
  background: linear-gradient(to top, var(--c-surface-1) 40%, transparent 100%);
  position: relative;
}
.agent-context-note {
  width: 100%;
  color: var(--c-text-3);
  font-size: 11px;
}
.agent-selected-skills {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}
.selected-skills-label {
  flex-shrink: 0;
  color: var(--c-text-3);
  font-size: 11px;
}
.selected-skill-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  padding: 4px 7px;
  border: 1px solid var(--c-accent);
  border-radius: 6px;
  background: var(--c-accent-bg);
  color: var(--c-accent-hover);
  font: inherit;
  font-size: 11px;
  cursor: pointer;
}
.selected-skill-chip span:first-child {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.selected-skill-chip:focus-visible {
  outline: 2px solid var(--c-accent);
  outline-offset: 2px;
}
.agent-composer {
  position: relative;
  width: 100%;
}
.agent-input-row {
  width: 100%;
  display: flex;
  gap: 6px;
  align-items: flex-end;
  background: var(--c-surface-2);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 24px;
  padding: 6px;
  box-shadow:
    0 16px 40px rgba(0, 0, 0, 0.3),
    inset 0 1px 1px rgba(255, 255, 255, 0.05);
  transition: all var(--motion-slow) var(--ease-out);
}
.agent-input-row:focus-within {
  border-color: rgba(91, 108, 255, 0.4);
  box-shadow:
    0 16px 48px rgba(91, 108, 255, 0.15),
    inset 0 1px 1px rgba(255, 255, 255, 0.1);
  background: var(--c-surface-3);
}
.agent-input {
  flex: 1;
  min-height: 42px;
  max-height: 116px;
  padding: 8px 12px;
  resize: vertical;
  border: none;
  background: transparent;
  color: var(--c-text-0);
  font-size: 14px;
  font-family: inherit;
  outline: none;
  box-shadow: none;
}
.agent-input:focus {
  border-color: transparent;
}
.agent-input:disabled {
  opacity: 0.5;
}
.agent-attach-btn {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: none;
  background: transparent;
  color: var(--c-text-2);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.15s;
}
.agent-attach-btn:hover:not(:disabled) {
  background: var(--c-surface-2);
  color: var(--c-text-0);
}
.agent-attach-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.agent-attach-btn.voice-active {
  background: var(--c-accent);
  color: #fff;
  animation: voice-pulse 1.5s ease-in-out infinite;
}
@keyframes voice-pulse {
  0%,
  100% {
    box-shadow: 0 0 0 0 rgba(var(--c-accent-rgb), 0.4);
  }
  50% {
    box-shadow: 0 0 0 6px rgba(var(--c-accent-rgb), 0);
  }
}
.agent-send-btn {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: none;
  background: var(--c-accent);
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 12px var(--accent-glow);
  transition:
    background 0.2s,
    box-shadow 0.2s,
    opacity 0.15s;
}
.agent-send-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.agent-send-btn:not(:disabled):hover {
  opacity: 0.85;
}
.agent-send-btn.stopping {
  background: var(--c-surface-3);
  box-shadow: 0 0 0 0 rgba(91, 108, 255, 0);
  animation: stop-ring 1.6s ease-out infinite;
}
@keyframes stop-ring {
  0% {
    box-shadow: 0 0 0 0 color-mix(in srgb, var(--c-accent) 50%, transparent);
  }
  70% {
    box-shadow: 0 0 0 8px transparent;
  }
  100% {
    box-shadow: 0 0 0 0 transparent;
  }
}

/* File attachments */
.agent-attachments {
  width: 100%;
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  padding: 6px 0;
}
.agent-file {
  display: flex;
  align-items: center;
  gap: 4px;
  background: var(--c-surface-2);
  border: 1px solid var(--c-surface-3);
  border-radius: 4px;
  padding: 3px 8px;
  font-size: 11px;
  color: var(--c-text-3);
}
.agent-file svg {
  flex-shrink: 0;
}
.agent-file-remove {
  background: none;
  border: none;
  color: var(--c-text-3);
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
  padding: 0 2px;
}
.agent-file-remove:hover {
  color: var(--c-danger);
}

/* Docs tab */
.agent-docs {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}
.docs-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.docs-toolbar-actions {
  display: flex;
  gap: 6px;
}
.docs-error {
  text-align: center;
  color: var(--c-danger);
  font-size: 12px;
  padding: 8px;
  background: var(--c-danger-bg);
  border-radius: 6px;
  margin-bottom: 8px;
}
.docs-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--c-text-0);
}
.docs-loading,
.docs-empty {
  text-align: center;
  color: var(--c-text-3);
  padding: 40px;
}
.docs-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.doc-card {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  background: var(--c-surface-2);
  border: 1px solid var(--c-surface-3);
  border-radius: 8px;
}
.doc-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.doc-title {
  font-size: 13px;
  color: var(--c-text-0);
}
.doc-meta {
  font-size: 11px;
  color: var(--c-text-3);
}
.doc-del-btn {
  background: none;
  border: none;
  color: var(--c-text-3);
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  display: flex;
  align-items: center;
}
.doc-del-btn:hover {
  color: var(--c-danger);
  background: var(--c-danger-bg);
}

/* Templates tab */
.agent-templates {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}
.skills-heading {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 2px;
}
.skills-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.skill-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 11px;
  border-bottom: 1px solid var(--c-border);
  background: transparent;
}
.skill-row.selected {
  border-radius: 8px;
  border-bottom-color: transparent;
  background: var(--c-accent-bg);
}
.skill-copy {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  gap: 3px;
}
.skill-name-row {
  display: flex;
  align-items: center;
  gap: 7px;
}
.skill-name {
  color: var(--c-text-0);
  font-size: 13px;
  font-weight: 650;
}
.skill-family {
  color: var(--brand-red);
  font-family: var(--font-serif);
  font-size: 10px;
  letter-spacing: 0.03em;
}
.skill-description {
  color: var(--c-text-3);
  font-size: 11px;
  line-height: 1.45;
}
.skill-row.selected {
  border-radius: 8px;
  border-bottom-color: transparent;
  background: var(--c-accent-bg);
}
.skill-copy {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  gap: 3px;
}
.skill-name-row {
  display: flex;
  align-items: center;
  gap: 7px;
}
.skill-name {
  color: var(--c-text-0);
  font-size: 13px;
  font-weight: 650;
}
.skill-family {
  color: var(--brand-red);
  font-family: var(--font-serif);
  font-size: 10px;
  letter-spacing: 0.03em;
}
.skill-description {
  color: var(--c-text-3);
  font-size: 11px;
  line-height: 1.45;
}
.skill-use-btn {
  flex-shrink: 0;
  padding: 5px 8px;
  border: 1px solid var(--c-border);
  border-radius: 6px;
  background: var(--c-panel);
  color: var(--c-text-2);
  font: inherit;
  font-size: 11px;
  cursor: pointer;
}
.skill-use-btn:hover {
  border-color: var(--c-accent);
  color: var(--c-accent);
}
.skill-use-btn:focus-visible {
  outline: 2px solid var(--c-accent);
  outline-offset: 2px;
}
.paper-template-section {
  margin-top: 18px;
  border-top: 1px solid var(--c-border);
  padding-top: 12px;
}
.paper-template-section > summary {
  color: var(--c-text-1);
  font-size: 12px;
  font-weight: 650;
  cursor: pointer;
}
.template-section-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 0;
  color: var(--c-text-3);
  font-size: 11px;
}
.template-empty {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 4px;
  color: var(--c-text-3);
  font-size: 11px;
}
.template-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}
.template-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  background: var(--c-surface-2);
  border: 1px solid var(--c-surface-3);
  border-radius: 8px;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: all 0.15s;
}
.template-card:hover {
  border-color: var(--c-accent-hover);
  background: var(--c-accent-bg2);
}
.template-icon {
  font-size: 24px;
}
.template-info {
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.template-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--c-text-0);
}
.template-venue {
  font-size: 11px;
  color: var(--c-text-3);
}
.template-preview {
  margin-top: 12px;
  padding: 12px;
  background: var(--c-surface-2);
  border: 1px solid var(--c-surface-3);
  border-radius: 8px;
}
.template-preview-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 14px;
  font-weight: 600;
  color: var(--c-text-0);
}
.template-preview-desc {
  font-size: 12px;
  color: var(--c-text-3);
  margin-top: 6px;
  line-height: 1.5;
}

/* Buttons (docs/templates tabs) */
.btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 12px;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  font-family: inherit;
}
.btn.ghost {
  background: transparent;
  color: var(--c-text-2);
}
.btn.ghost:hover {
  color: var(--c-accent-hover);
}
.btn.ghost:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.btn.primary {
  background: var(--c-accent);
  color: #fff;
}
.btn.primary:hover {
  opacity: 0.88;
}

/* Workspace status bar */
.agent-workspace-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  font-size: 11px;
  border-bottom: 1px solid var(--c-glass-border);
  background: transparent;
}
.ws-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--c-text-3);
  flex-shrink: 0;
}
.agent-workspace-bar.active .ws-dot {
  background: #4ade80;
}
.ws-name {
  color: var(--c-text-2);
  font-family: var(--font-mono, monospace);
}
.ws-name.muted {
  color: var(--c-text-3);
  font-style: italic;
}
.docs-subtitle {
  font-size: 11px;
  color: var(--c-text-3);
  margin-top: 2px;
}
.hint.warn {
  color: var(--c-warn, #f59e0b);
}

/* Reference-driven task panel. The event stream remains real Agent V2 data. */
.agent-panel {
  top: 0;
  width: min(460px, calc(100vw - 76px));
  height: 100vh;
  margin-top: 0;
  border-left: 1px solid var(--c-border);
  background: var(--c-panel);
  box-shadow: var(--elevation-3);
  backdrop-filter: none;
  transition: transform var(--motion-page) var(--ease-out);
}
.agent-panel.standalone {
  border: 0;
  border-radius: 0;
  box-shadow: none;
}
.agent-panel.floating {
  border: 1px solid var(--c-border);
  border-radius: 11px;
  background: var(--c-panel);
  box-shadow: var(--elevation-4);
}
.agent-header {
  min-height: 70px;
  box-sizing: border-box;
  gap: 10px;
  padding: 27px 54px 12px 16px;
  border-bottom: 1px solid var(--c-border);
  background: var(--c-panel);
}
.agent-tabs {
  gap: 0;
  padding: 3px;
  border-radius: 8px;
  background: var(--c-surface-2);
}
.agent-tab {
  flex: 1;
  min-width: 0;
  padding: 6px 7px;
  border-radius: 6px;
  font-size: 11px;
}
.agent-tab.active {
  background: var(--c-panel);
  box-shadow: var(--elevation-1);
}
.agent-chat {
  background: var(--c-app-bg);
}
.agent-messages {
  gap: 14px;
  padding: 18px;
}
.agent-empty {
  padding: 52px 20px;
}
.agent-empty p:first-child {
  color: var(--c-text-1);
  font-family: var(--font-sans);
  font-size: 14px;
  font-style: normal;
}
.agent-msg {
  width: 100%;
  max-width: 100%;
}
.agent-msg.user {
  align-self: stretch;
}
.agent-bubble {
  border-radius: 8px;
}
.agent-msg.user .agent-bubble {
  padding: 11px 12px;
  border: 1px solid var(--c-border);
  border-left: 3px solid var(--c-accent);
  border-radius: 8px;
  background: var(--c-panel);
  color: var(--c-text-0);
  box-shadow: none;
}
.agent-msg.assistant .agent-bubble {
  padding: 12px 2px 4px;
  border-top: 1px solid var(--c-border);
  font-size: 13px;
  line-height: 1.65;
}
.agent-markdown {
  white-space: normal;
}
.agent-markdown :deep(p) {
  margin: 0 0 9px;
}
.agent-markdown :deep(p:last-child) {
  margin-bottom: 0;
}
.agent-markdown :deep(h1),
.agent-markdown :deep(h2),
.agent-markdown :deep(h3) {
  margin: 14px 0 7px;
  font-family: var(--font-sans), var(--font-zh);
  font-size: 14px;
  line-height: 1.4;
}
.agent-markdown :deep(ul),
.agent-markdown :deep(ol) {
  margin: 6px 0 10px;
  padding-left: 20px;
}
.agent-markdown :deep(li) {
  margin: 3px 0;
}
.agent-markdown :deep(code) {
  padding: 1px 4px;
  border-radius: 4px;
  background: var(--c-surface-2);
  font-family: var(--font-mono);
  font-size: 12px;
}
.agent-markdown :deep(pre) {
  margin: 9px 0;
  padding: 10px;
  overflow: auto;
  border: 1px solid var(--c-border);
  border-radius: 7px;
  background: var(--c-surface-2);
}
.agent-markdown :deep(pre code) {
  padding: 0;
  background: transparent;
}
.agent-markdown :deep(table) {
  width: 100%;
  margin: 9px 0;
  border-collapse: collapse;
  font-size: 12px;
}
.agent-markdown :deep(th),
.agent-markdown :deep(td) {
  padding: 6px 7px;
  border: 1px solid var(--c-border);
  text-align: left;
  vertical-align: top;
}
.agent-markdown :deep(th) {
  background: var(--c-surface-2);
  font-weight: 650;
}
.agent-event {
  margin-bottom: 6px;
  padding: 9px 10px;
  border-color: var(--c-border);
  border-radius: 7px;
  background: var(--c-panel);
  box-shadow: none;
  backdrop-filter: none;
}
.agent-event.tool-call,
.agent-event.tool-result,
.agent-event.tool-result.evt-error,
.agent-event.task-lifecycle,
.agent-event.task-lifecycle.done,
.agent-event.warning {
  background: var(--c-panel);
}
.evt-risk-badge {
  border-radius: 4px;
}
.agent-thinking-bar {
  background: var(--c-accent);
  animation: none;
  opacity: 0.7;
}
.agent-status-bar {
  padding: 7px 10px;
  border: 1px solid var(--c-border);
  border-radius: 7px;
  background: var(--c-panel);
}
.agent-status-bar::after {
  display: none;
}
.agent-input-area {
  gap: 7px;
  padding: 12px 14px 16px;
  border-top: 1px solid var(--c-border);
  background: var(--c-panel);
}
.agent-input-row {
  padding: 4px;
  border-color: var(--c-border);
  border-radius: 9px;
  background: var(--input-bg);
  box-shadow: none;
}
.agent-input-row:focus-within {
  border-color: var(--c-accent);
  background: var(--input-bg);
  box-shadow: var(--ring-focus);
}
.agent-attach-btn,
.agent-send-btn {
  width: 34px;
  height: 34px;
  border-radius: 7px;
  box-shadow: none;
}
.agent-workspace-bar {
  padding: 3px 0;
  border: 0;
}
.agent-docs,
.agent-templates,
.agent-sessions {
  background: var(--c-app-bg);
}
.doc-card,
.template-card,
.template-preview {
  border-color: var(--c-border);
  background: var(--c-panel);
}

@media (max-width: 640px) {
  .agent-panel {
    width: calc(100vw - 76px);
  }
  .agent-header {
    padding-right: 12px;
  }
  .agent-tab {
    font-size: 10px;
  }
}
@media (max-width: 1280px) {
  .agent-panel.embedded {
    position: absolute;
    z-index: 700;
    top: 0;
    right: 0;
    width: min(420px, calc(100% - 16px));
    height: 100%;
    transform: translateX(102%);
    border-left: 1px solid var(--c-border);
    box-shadow: -18px 0 46px var(--c-shadow);
    visibility: hidden;
    transition:
      transform var(--motion-page) var(--ease-out),
      visibility 0s linear var(--motion-page);
  }
  .agent-panel.embedded.open {
    width: min(420px, calc(100% - 16px));
    transform: translateX(0);
    visibility: visible;
    transition:
      transform var(--motion-page) var(--ease-out),
      visibility 0s;
  }
}
@media (max-width: 640px) {
  .agent-panel.embedded,
  .agent-panel.embedded.open {
    width: 100%;
  }
}
</style>
