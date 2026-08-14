const isDev = import.meta.env.DEV

export const logger = {
  debug: (...args: unknown[]) => {
    // eslint-disable-next-line no-console -- 有意的调试日志，仅 dev 环境输出
    if (isDev) console.log(...args)
  },
  warn: (...args: unknown[]) => {
    if (isDev) console.warn(...args)
  },
  error: (...args: unknown[]) => {
    console.error(...args)
  },
}
