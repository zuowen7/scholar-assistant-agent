import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createI18n } from 'vue-i18n'

import { createAppI18n } from '../i18n'
import zhMessages from '../i18n/locales/zh-CN.json'
import enMessages from '../i18n/locales/en-US.json'

function getAllKeys(obj: Record<string, unknown>, prefix = ''): string[] {
  const keys: string[] = []
  for (const key of Object.keys(obj)) {
    const fullKey = prefix ? `${prefix}.${key}` : key
    if (typeof obj[key] === 'object' && obj[key] !== null) {
      keys.push(...getAllKeys(obj[key] as Record<string, unknown>, fullKey))
    } else {
      keys.push(fullKey)
    }
  }
  return keys.sort()
}

describe('i18n setup', () => {
  it('creates i18n instance with zh-CN as default locale', () => {
    const i18n = createAppI18n()
    expect(i18n.global.locale.value).toBe('zh-CN')
  })

  it('creates a vue-i18n instance', () => {
    const i18n = createAppI18n()
    // vue-i18n createI18n returns an object with .global
    expect(i18n.global).toBeDefined()
    expect(typeof i18n.global.t).toBe('function')
  })

  it('has zh-CN and en-US messages loaded', () => {
    const i18n = createAppI18n()
    expect(i18n.global.getLocaleMessage('zh-CN')).toBeDefined()
    expect(i18n.global.getLocaleMessage('en-US')).toBeDefined()
  })

  it('all zh-CN keys have corresponding en-US keys', () => {
    const zhKeys = getAllKeys(zhMessages)
    const enKeys = getAllKeys(enMessages)
    expect(enKeys).toEqual(zhKeys)
  })

  it('can translate a known key in both locales', () => {
    const i18n = createAppI18n()
    i18n.global.locale.value = 'zh-CN'
    expect(typeof i18n.global.t('mode.translate')).toBe('string')
    i18n.global.locale.value = 'en-US'
    expect(typeof i18n.global.t('mode.translate')).toBe('string')
  })
})
