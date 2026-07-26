<template>
  <div class="home-view">
    <EditorWelcome
      @new-project="showProjectStart = true"
      @open-template="showTemplatePicker = true"
      @open-folder="openWorkspaceFolder"
      @new-document="openLooseDraft"
      @quick-translate="workspace.openStandaloneTranslation"
      @open-recent="openRecentProject"
    />

    <EditorNewProject
      :visible="showProjectStart"
      @close="showProjectStart = false"
      @project-created="handleProjectCreated"
    />
    <TemplatePicker
      :visible="showTemplatePicker"
      :is-dark="isDark"
      @close="showTemplatePicker = false"
      @create="handleTemplateCreate"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { open as openDialog } from '@tauri-apps/plugin-dialog'
import EditorWelcome from './EditorWelcome.vue'
import EditorNewProject from './EditorNewProject.vue'
import TemplatePicker from './TemplatePicker.vue'
import { useEditor } from '../composables/useEditor'
import { useFileTree } from '../composables/useFileTree'
import { useProject } from '../composables/useProject'
import { useProjectWorkspace } from '../composables/useProjectWorkspace'
import { useWorkspaceNavigation } from '../composables/useWorkspaceNavigation'
import { useToast } from '../composables/useToast'

defineProps<{ isDark?: boolean }>()

const showProjectStart = ref(false)
const showTemplatePicker = ref(false)
const workspace = useWorkspaceNavigation()
const editor = useEditor()
const fileTree = useFileTree()
const project = useProject()
const { openProjectWorkspace } = useProjectWorkspace()
const { pushError } = useToast()

async function handleProjectCreated(path: string) {
  showProjectStart.value = false
  try {
    await openProjectWorkspace(path, { draftView: 'editor' })
  } catch (error) {
    pushError(error instanceof Error ? error.message : '无法打开新项目')
  }
}

async function openRecentProject(path: string) {
  try {
    await openProjectWorkspace(path, { restoreView: true })
  } catch (error) {
    pushError(error instanceof Error ? error.message : '无法打开最近项目')
  }
}

async function openWorkspaceFolder() {
  try {
    const selected = await openDialog({ directory: true, multiple: false })
    if (typeof selected !== 'string') return
    if (await project.detectProject(selected)) {
      await openProjectWorkspace(selected, { restoreView: true })
      return
    }
    await fileTree.openFolder(selected)
    editor.openNewUntitled()
    workspace.enterWorkspace(selected, { draftView: 'editor' })
  } catch (error) {
    pushError(error instanceof Error ? error.message : '无法打开工作区')
  }
}

function openLooseDraft() {
  editor.openNewUntitled()
  workspace.enterWorkspace(fileTree.rootDir.value, { draftView: 'editor' })
}

function handleTemplateCreate(markdown: string, templateId: string) {
  showTemplatePicker.value = false
  editor.openNewUntitled()
  if (editor.activeTab.value) {
    editor.activeTab.value.content = markdown
    editor.activeTab.value.name = `${templateId}-paper.md`
  }
  workspace.enterWorkspace(fileTree.rootDir.value, { draftView: 'editor' })
}
</script>

<style scoped>
.home-view {
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
}
</style>
