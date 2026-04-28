import { ref } from 'vue'
import type { FileEntry } from '../types'

const files = ref<FileEntry[]>([])
const rootDir = ref<string | null>(null)

export function useFileTree() {
  async function openFolder(dirPath: string) {
    rootDir.value = dirPath
    files.value = await readDir(dirPath)
  }

  async function readDir(dirPath: string): Promise<FileEntry[]> {
    try {
      const { readDir: tauriReadDir } = await import('@tauri-apps/plugin-fs')
      const entries = await tauriReadDir(dirPath)
      const result: FileEntry[] = []
      for (const entry of entries) {
        if (entry.name?.startsWith('.')) continue
        const isDir = entry.isDirectory
        const entryPath = `${dirPath}/${entry.name}`
        const fileEntry: FileEntry = {
          name: entry.name,
          path: entryPath,
          isDir,
        }
        if (isDir) {
          fileEntry.children = await readDir(fileEntry.path)
        }
        result.push(fileEntry)
      }
      result.sort((a, b) => {
        if (a.isDir !== b.isDir) return a.isDir ? -1 : 1
        return a.name.localeCompare(b.name)
      })
      return result
    } catch {
      return []
    }
  }

  async function readFileContent(path: string): Promise<string> {
    const { readTextFile } = await import('@tauri-apps/plugin-fs')
    return readTextFile(path)
  }

  async function writeFile(path: string, content: string): Promise<void> {
    const { writeTextFile } = await import('@tauri-apps/plugin-fs')
    await writeTextFile(path, content)
  }

  async function createFile(dirPath: string, name: string): Promise<string> {
    const path = `${dirPath}/${name}`
    await writeFile(path, '')
    if (rootDir.value) {
      files.value = await readDir(rootDir.value)
    }
    return path
  }

  async function renameFile(oldPath: string, newName: string): Promise<string> {
    const { rename } = await import('@tauri-apps/plugin-fs')
    const lastSep = Math.max(oldPath.lastIndexOf('/'), oldPath.lastIndexOf('\\'))
    const dir = oldPath.substring(0, lastSep)
    const sep = oldPath.includes('\\') ? '\\' : '/'
    const newPath = `${dir}${sep}${newName}`
    await rename(oldPath, newPath)
    if (rootDir.value) {
      files.value = await readDir(rootDir.value)
    }
    return newPath
  }

  async function deleteFile(path: string): Promise<void> {
    const { remove } = await import('@tauri-apps/plugin-fs')
    await remove(path)
    if (rootDir.value) {
      files.value = await readDir(rootDir.value)
    }
  }

  return {
    files,
    rootDir,
    openFolder,
    readDir,
    readFileContent,
    writeFile,
    createFile,
    renameFile,
    deleteFile,
  }
}
