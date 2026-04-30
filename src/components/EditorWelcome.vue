<template>
  <div class="editor-welcome">
    <div class="welcome-content">
      <div class="welcome-hero">
        <GraduationCap :size="36" class="hero-icon" />
        <div class="hero-text">
          <p class="hero-kicker">研墨工作台</p>
          <h1 class="hero-title">开始写作</h1>
        </div>
      </div>

      <p class="welcome-section-label">快速开始</p>
      <div class="welcome-cards">
        <button class="wc-card" @click="$emit('new-project')">
          <span class="wc-icon"><Workflow :size="18" /></span>
          <div class="wc-text">
            <strong>新建工程</strong>
            <span>思维导图 → 论文草稿</span>
          </div>
        </button>
        <button class="wc-card" @click="$emit('open-template')">
          <span class="wc-icon accent"><FileText :size="18" /></span>
          <div class="wc-text">
            <strong>从模板新建</strong>
            <span>IEEE / ACM / 自定义</span>
          </div>
        </button>
        <button class="wc-card" @click="$emit('open-folder')">
          <span class="wc-icon"><FolderOpen :size="18" /></span>
          <div class="wc-text">
            <strong>打开文件夹</strong>
            <span>继续现有工程</span>
          </div>
        </button>
        <button class="wc-card" @click="$emit('new-document')">
          <span class="wc-icon"><FilePlus :size="18" /></span>
          <div class="wc-text">
            <strong>空白文档</strong>
            <span>直接进入编辑器</span>
          </div>
        </button>
      </div>

      <div class="welcome-shortcuts">
        <kbd>Ctrl+K</kbd> AI 编辑 &nbsp;·&nbsp; <kbd>Ctrl+S</kbd> 保存 &nbsp;·&nbsp; <kbd>Tab</kbd> 接受补全
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { GraduationCap, Workflow, FileText, FolderOpen, FilePlus } from './ui/icons'

defineEmits<{
  'new-project': []
  'open-template': []
  'open-folder': []
  'new-document': []
}>()
</script>

<style scoped>
.editor-welcome {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-7) var(--space-6);
  background: var(--editor-bg);
  overflow-y: auto;
}

.welcome-content { width: min(480px, 100%); }

.welcome-hero {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  margin-bottom: var(--space-6);
}

.hero-icon { color: var(--c-accent); flex-shrink: 0; }

.hero-kicker {
  margin: 0 0 2px;
  color: var(--c-accent);
  font-size: var(--text-xs);
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.hero-title {
  margin: 0;
  font-size: var(--text-3xl);
  font-weight: 700;
  color: var(--c-text-0);
  line-height: var(--leading-tight);
}

.welcome-section-label {
  font-size: var(--text-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--c-text-3);
  margin-bottom: var(--space-2);
}

.welcome-cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-2);
  margin-bottom: var(--space-5);
}

.wc-card {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-3);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--toolbar-bg);
  color: var(--c-text-1);
  cursor: pointer;
  font: inherit;
  text-align: left;
  transition: border-color var(--motion-fast), background var(--motion-fast);
}
.wc-card:hover { border-color: var(--c-accent); background: var(--hover-bg); }

.wc-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  background: var(--c-surface-3);
  color: var(--c-text-2);
  flex-shrink: 0;
}
.wc-icon.accent { background: var(--c-accent-soft); color: var(--c-accent); }
.wc-card:hover .wc-icon { background: var(--c-accent-soft); color: var(--c-accent); }

.wc-text { display: flex; flex-direction: column; gap: 2px; }
.wc-text strong { font-size: var(--text-md); font-weight: 600; }
.wc-text span { font-size: var(--text-sm); color: var(--c-text-3); }

.welcome-shortcuts {
  font-size: var(--text-sm);
  color: var(--c-text-3);
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}
.welcome-shortcuts kbd {
  display: inline-flex;
  align-items: center;
  height: 20px;
  padding: 0 6px;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  background: var(--c-surface-4);
  color: var(--c-text-2);
  font: inherit;
  font-size: 11px;
}
</style>
