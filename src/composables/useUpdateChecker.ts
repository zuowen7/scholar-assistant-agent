import { API_BASE } from '../utils/api'
import { useToast } from './useToast'

const GITHUB_REPO = 'zuowen7/scholar-assistant-agent'
const NOTIFIED_KEY = 'lastNotifiedVersion'

export function compareVersions(local: string, remote: string): number {
  const l = local.replace(/^v/, '').split('.').map(Number)
  const r = remote.replace(/^v/, '').split('.').map(Number)
  for (let i = 0; i < 3; i++) {
    if ((r[i] ?? 0) > (l[i] ?? 0)) return -1
    if ((r[i] ?? 0) < (l[i] ?? 0)) return 1
  }
  return 0
}

export async function checkForUpdate(): Promise<void> {
  let localVersion: string
  try {
    const res = await fetch(`${API_BASE}/api/health`)
    if (!res.ok) return
    const data = await res.json()
    localVersion = data.version
    if (!localVersion) return
  } catch {
    return
  }

  try {
    const res = await fetch(
      `https://api.github.com/repos/${GITHUB_REPO}/releases/latest`
    )
    if (!res.ok) return
    const data = await res.json()
    const remoteVersion = data.tag_name?.replace(/^v/, '')
    if (!remoteVersion) return

    if (compareVersions(localVersion, remoteVersion) < 0) {
      const alreadyNotified = localStorage.getItem(NOTIFIED_KEY)
      if (alreadyNotified === remoteVersion) return

      const { info } = useToast()
      info(`新版本 v${remoteVersion} 已发布，前往 GitHub Releases 下载`, 8000)
      localStorage.setItem(NOTIFIED_KEY, remoteVersion)
    }
  } catch {
    return
  }
}
