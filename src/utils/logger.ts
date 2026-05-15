type LogLevel = 'debug' | 'info' | 'warn' | 'error'

const _isDev = import.meta.env.DEV

function _ts(): string {
  return new Date().toISOString()
}

function _log(level: LogLevel, msg: string, ctx?: Record<string, unknown>): void {
  if (!_isDev && (level === 'debug' || level === 'info')) return
  const payload = ctx ? ` ${JSON.stringify(ctx)}` : ''
  const formatted = `[${_ts()}] [${level.toUpperCase()}] ${msg}${payload}`
  switch (level) {
    case 'error': console.error(formatted); break
    case 'warn': console.warn(formatted); break
    case 'info': console.info(formatted); break
    default: console.log(formatted)
  }
}

export const logger = {
  debug: (msg: string, ctx?: Record<string, unknown>) => _log('debug', msg, ctx),
  info: (msg: string, ctx?: Record<string, unknown>) => _log('info', msg, ctx),
  warn: (msg: string, ctx?: Record<string, unknown>) => _log('warn', msg, ctx),
  error: (msg: string, ctx?: Record<string, unknown>) => _log('error', msg, ctx),
}
