const ENV_API_URL = import.meta.env.VITE_API_URL as string | undefined

const _url = ENV_API_URL || 'http://127.0.0.1:18088'
if (ENV_API_URL && !/^https?:\/\//i.test(ENV_API_URL)) {
  throw new Error(`[api] VITE_API_URL="${ENV_API_URL}" must start with http:// or https://`)
}
export const API_BASE = _url.replace(/\/$/, '')
