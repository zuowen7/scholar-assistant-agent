import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

vi.mock('../utils/api', () => ({ API_BASE: '' }))

import ZoteroSettings from '../components/settings/ZoteroSettings.vue'

describe('ZoteroSettings', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('loads the redacted key state and existing user id', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          zotero: { api_key: 'zot****key', user_id: '123456', style: 'apa' },
        }),
      }),
    )

    const wrapper = mount(ZoteroSettings)
    await flushPromises()

    expect(wrapper.get('[data-test="zotero-api-key"]').attributes('placeholder')).toBe(
      'settings.zoteroKeyStored',
    )
    expect((wrapper.get('[data-test="zotero-user-id"]').element as HTMLInputElement).value).toBe(
      '123456',
    )
    expect((wrapper.get('[data-test="zotero-style"]').element as HTMLSelectElement).value).toBe(
      'apa',
    )
  })

  it('preserves the stored API key when saving a changed user id', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          zotero: { api_key: 'zot****key', user_id: '123456', style: 'ieee' },
        }),
      })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ zotero: {} }) })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(ZoteroSettings)
    await flushPromises()
    await wrapper.get('[data-test="zotero-user-id"]').setValue('654321')
    await wrapper.get('[data-test="zotero-save"]').trigger('click')
    await flushPromises()

    const request = fetchMock.mock.calls[1]
    expect(request[0]).toBe('/api/config')
    expect(request[1].method).toBe('PUT')
    expect(JSON.parse(request[1].body)).toEqual({
      zotero: { user_id: '654321', style: 'ieee' },
    })
    expect(wrapper.get('[data-test="zotero-status"]').text()).toContain('settings.zoteroSaved')
  })

  it('checks the real Zotero connection through the verification endpoint', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          zotero: { api_key: 'zot****key', user_id: '123456', style: 'ieee' },
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ connected: true, verified: true }),
      })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(ZoteroSettings)
    await flushPromises()
    await wrapper.get('[data-test="zotero-check"]').trigger('click')
    await flushPromises()

    expect(fetchMock.mock.calls[1][0]).toBe('/api/zotero/status?verify=true')
    expect(wrapper.get('[data-test="zotero-status"]').text()).toContain('settings.zoteroConfigured')
  })
})
