import { API_BASE } from '../utils/api'
import { useToast } from './useToast'
import { i18n } from '../i18n'

const GITHUB_REPO = 'zuowen7/scholar-assistant-agent'
const NOTIFIED_KEY = 'lastNotifiedVersion'

export interface UpdateCheckResult {
  status: 'available' | 'current'
  localVersion: string
  remoteVersion: string
  releaseUrl: string
}

export function compareVersions(local: string, remote: string): number {
  const l = local.replace(/^v/, '').split('.').map(Number)
  const r = remote.replace(/^v/, '').split('.').map(Number)
  for (let i = 0; i < 3; i++) {
    if ((r[i] ?? 0) > (l[i] ?? 0)) return -1
    if ((r[i] ?? 0) < (l[i] ?? 0)) return 1
  }
  return 0
}

export async function checkForUpdate(
  options: { notify?: boolean } = {},
): Promise<UpdateCheckResult | undefined> {
  const notify = options.notify !== false
  let localVersion: string
  try {
    const res = await fetch(`${API_BASE}/api/health`)
    if (!res.ok) return undefined
    const data = await res.json()
    localVersion = data.version
    if (!localVersion) return undefined
  } catch {
    return undefined
  }

  try {
    const res = await fetch(`https://api.github.com/repos/${GITHUB_REPO}/releases/latest`)
    if (!res.ok) return undefined
    const data = await res.json()
    const remoteVersion = data.tag_name?.replace(/^v/, '')
    if (!remoteVersion) return undefined

    const result: UpdateCheckResult = {
      status: compareVersions(localVersion, remoteVersion) < 0 ? 'available' : 'current',
      localVersion,
      remoteVersion,
      releaseUrl: data.html_url || `https://github.com/${GITHUB_REPO}/releases/latest`,
    }

    if (result.status === 'available' && notify) {
      const alreadyNotified = localStorage.getItem(NOTIFIED_KEY)
      if (alreadyNotified === remoteVersion) return result

      const { info } = useToast()
      info(i18n.global.t('settingsCenter.updateAvailable', { version: remoteVersion }), 8000)
      localStorage.setItem(NOTIFIED_KEY, remoteVersion)
    }
    return result
  } catch {
    return undefined
  }
}
