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

interface LatestReleasePayload {
  ok?: boolean
  latest_version?: string
  release_url?: string
}

export async function checkForUpdate(
  options: { notify?: boolean } = {},
): Promise<UpdateCheckResult | undefined> {
  const notify = options.notify !== false
  let localVersion: string
  let remoteVersion: string
  let releaseUrl: string
  try {
    // 本地版本来自后端 /api/health，远端版本经后端 /api/version/latest 代理查询。
    // 前端不直连 api.github.com：打包后会被 Tauri CSP 拦截，且匿名 API 限流严重。
    const res = await fetch(`${API_BASE}/api/health`)
    if (!res.ok) return undefined
    const health = await res.json()
    localVersion = health.version
    if (!localVersion) return undefined

    const res2 = await fetch(`${API_BASE}/api/version/latest`)
    if (!res2.ok) return undefined
    const latest = (await res2.json()) as LatestReleasePayload
    if (!latest?.ok || !latest.latest_version) return undefined
    remoteVersion = latest.latest_version.replace(/^v/, '')
    releaseUrl = latest.release_url || `https://github.com/${GITHUB_REPO}/releases/latest`
  } catch {
    return undefined
  }

  const result: UpdateCheckResult = {
    status: compareVersions(localVersion, remoteVersion) < 0 ? 'available' : 'current',
    localVersion,
    remoteVersion,
    releaseUrl,
  }

  if (result.status === 'available' && notify) {
    const alreadyNotified = localStorage.getItem(NOTIFIED_KEY)
    if (alreadyNotified === remoteVersion) return result

    const { info } = useToast()
    info(i18n.global.t('settingsCenter.updateAvailable', { version: remoteVersion }), 8000)
    localStorage.setItem(NOTIFIED_KEY, remoteVersion)
  }
  return result
}
