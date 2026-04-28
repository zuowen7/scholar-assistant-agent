const ENV_API_URL = import.meta.env.VITE_API_URL as string | undefined

// In dev mode, use relative URLs so fetch() goes through Vite's dev-server proxy
// (which doesn't respect HTTP_PROXY env vars that WebView2 would route through).
// In production, connect directly — proxy vars are cleared by main.rs at startup.
const _url = ENV_API_URL || (import.meta.env.DEV ? '' : 'http://127.0.0.1:18088')
if (ENV_API_URL && !/^https?:\/\//i.test(ENV_API_URL)) {
  throw new Error(`[api] VITE_API_URL="${ENV_API_URL}" must start with http:// or https://`)
}
export const API_BASE = _url.replace(/\/$/, '')
