const ENV_API_URL = import.meta.env.VITE_API_URL as string | undefined

const _url = ENV_API_URL || 'http://127.0.0.1:18088'
if (_url && !/^https?:\/\//i.test(_url)) {
  console.warn(`[api] VITE_API_URL="${_url}" missing protocol, treating as relative path`)
}
export const API_BASE = _url.replace(/\/$/, '')
