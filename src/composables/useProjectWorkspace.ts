import type { DraftView } from './useWorkspaceNavigation'
import { useEditor } from './useEditor'
import { useFileTree } from './useFileTree'
import { useProject } from './useProject'
import { useWorkspaceNavigation } from './useWorkspaceNavigation'

function mainMarkdownPath(projectPath: string): string {
  return `${projectPath.replace(/\\/g, '/').replace(/\/+$/, '')}/draft/main.md`
}

export async function openProjectWorkspace(
  projectPath: string,
  options: { draftView?: DraftView; restoreView?: boolean } = {},
) {
  const normalizedPath = projectPath.replace(/\\/g, '/').replace(/\/+$/, '')
  const project = useProject()
  const fileTree = useFileTree()
  const editor = useEditor()
  const workspace = useWorkspaceNavigation()

  await project.openProject(projectPath)
  const mainMd = mainMarkdownPath(normalizedPath)
  try {
    const text = await fileTree.readFileContent(mainMd)
    editor.openFile(mainMd, text)
  } catch {
    editor.openNewUntitled()
  }
  workspace.enterWorkspace(normalizedPath, {
    section: 'draft',
    draftView: options.draftView,
    restoreView: options.restoreView,
  })
}

export function useProjectWorkspace() {
  return { openProjectWorkspace }
}

export { mainMarkdownPath as _mainMarkdownPathForTesting }
