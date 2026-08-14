import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

vi.mock('../utils/api', () => ({ API_BASE: '' }))

import VisionSettings from '../components/settings/VisionSettings.vue'

describe('VisionSettings', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('loads the redacted key state, base url, and model', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          vision: {
            api_key: 'visi****1234',
            base_url: 'https://open.bigmodel.cn/api/paas/v4',
            model: 'glm-4v-flash',
          },
        }),
      }),
    )

    const wrapper = mount(VisionSettings)
    await flushPromises()

    expect(wrapper.get('[data-test="vision-api-key"]').attributes('placeholder')).toBe(
      'settings.visionKeyStored',
    )
    expect((wrapper.get('[data-test="vision-base-url"]').element as HTMLInputElement).value).toBe(
      'https://open.bigmodel.cn/api/paas/v4',
    )
    expect((wrapper.get('[data-test="vision-model"]').element as HTMLInputElement).value).toBe(
      'glm-4v-flash',
    )
  })

  it('preserves the stored API key when saving a changed model', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          vision: {
            api_key: 'visi****1234',
            base_url: 'https://open.bigmodel.cn/api/paas/v4',
            model: 'glm-4v-flash',
          },
        }),
      })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ vision: {} }) })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(VisionSettings)
    await flushPromises()
    await wrapper.get('[data-test="vision-model"]').setValue('gpt-4o')
    await wrapper.get('[data-test="vision-save"]').trigger('click')
    await flushPromises()

    const request = fetchMock.mock.calls[1]
    expect(request[0]).toBe('/api/config')
    expect(request[1].method).toBe('PUT')
    expect(JSON.parse(request[1].body)).toEqual({
      vision: {
        base_url: 'https://open.bigmodel.cn/api/paas/v4',
        model: 'gpt-4o',
      },
    })
    expect(wrapper.get('[data-test="vision-status"]').text()).toContain('settings.visionSaved')
  })

  it('sends a new API key when one is entered', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ vision: { api_key: '', base_url: '', model: '' } }),
      })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ vision: {} }) })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(VisionSettings)
    await flushPromises()
    await wrapper.get('[data-test="vision-base-url"]').setValue('https://api.openai.com/v1')
    await wrapper.get('[data-test="vision-model"]').setValue('gpt-4o')
    await wrapper.get('[data-test="vision-api-key"]').setValue('sk-new-vision-key')
    await wrapper.get('[data-test="vision-save"]').trigger('click')
    await flushPromises()

    const request = fetchMock.mock.calls[1]
    expect(JSON.parse(request[1].body)).toEqual({
      vision: {
        base_url: 'https://api.openai.com/v1',
        model: 'gpt-4o',
        api_key: 'sk-new-vision-key',
      },
    })
    expect(wrapper.get('[data-test="vision-status"]').text()).toContain('settings.visionSaved')
  })

  it('disables save until base url and model are present', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ vision: { api_key: '', base_url: '', model: '' } }),
      }),
    )

    const wrapper = mount(VisionSettings)
    await flushPromises()

    expect(wrapper.get('[data-test="vision-save"]').attributes('disabled')).toBeDefined()
  })
})
