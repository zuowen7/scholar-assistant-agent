const ENV_API_URL = import.meta.env.VITE_API_URL as string | undefined

export const API_BASE = (ENV_API_URL || 'http://127.0.0.1:18088').replace(/\/$/, '')
