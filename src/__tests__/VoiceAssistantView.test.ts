/**
 * Tests for VoiceAssistantView.vue
 *
 * TDD tests for the Siri-style voice assistant overlay component.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import VoiceAssistantView from '../components/VoiceAssistantView.vue'

// ── Mocks ──────────────────────────────────────────────────────────────

const mockState = ref<string>('idle')
const mockTranscript = ref('')
const mockResponse = ref('')
const mockError = ref('')
const mockCancel = vi.fn()

vi.mock('../composables/useVoiceCommand', () => ({
  useVoiceCommand: () => ({
    state: mockState,
    transcript: mockTranscript,
    response: mockResponse,
    error: mockError,
    cancel: mockCancel,
    triggerVoiceCommand: vi.fn(),
    setProcessing: vi.fn(),
    done: vi.fn(),
  }),
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

// ── Tests ──────────────────────────────────────────────────────────────

describe('VoiceAssistantView', () => {
  beforeEach(() => {
    mockState.value = 'listening'
    mockTranscript.value = ''
    mockResponse.value = ''
    mockError.value = ''
    mockCancel.mockReset()
  })

  function mountView() {
    return mount(VoiceAssistantView, {
      global: {
        stubs: {
          'lucide-vue-next': false,
          Mic: true,
          Transition: {
            props: ['name'],
            template: '<slot />',
          },
        },
      },
    })
  }

  // ── Listening state ──────────────────────────────────────────────────

  it('renders overlay in listening state', () => {
    mockState.value = 'listening'
    const wrapper = mountView()
    expect(wrapper.find('.va-overlay').exists()).toBe(true)
    expect(wrapper.find('.va-orb').exists()).toBe(true)
  })

  it('shows listening status text', () => {
    mockState.value = 'listening'
    const wrapper = mountView()
    const status = wrapper.find('.va-status')
    expect(status.exists()).toBe(true)
    expect(status.text()).toContain('voice.listening')
  })

  it('displays transcript text', async () => {
    mockState.value = 'listening'
    mockTranscript.value = '把这段翻译成英文'
    const wrapper = mountView()
    await nextTick()
    expect(wrapper.find('.va-transcript').text()).toBe('把这段翻译成英文')
  })

  // ── Submitting state ─────────────────────────────────────────────────

  it('shows processing indicator in submitting state', () => {
    mockState.value = 'submitting'
    const wrapper = mountView()
    expect(wrapper.find('.va-status').text()).toContain('voice.processing')
  })

  // ── Processing state ─────────────────────────────────────────────────

  it('shows response text in processing state', async () => {
    mockState.value = 'processing'
    mockResponse.value = '好的，我来帮你翻译'
    const wrapper = mountView()
    await nextTick()
    expect(wrapper.find('.va-response').text()).toContain('好的，我来帮你翻译')
  })

  // ── Error display ────────────────────────────────────────────────────

  it('shows error message when error is set', async () => {
    mockState.value = 'listening'
    mockError.value = '语音识别不可用'
    const wrapper = mountView()
    await nextTick()
    expect(wrapper.find('.va-error').text()).toContain('语音识别不可用')
  })

  // ── Interaction ──────────────────────────────────────────────────────

  it('clicking backdrop calls cancel', async () => {
    mockState.value = 'listening'
    const wrapper = mountView()
    await wrapper.find('.va-backdrop').trigger('click')
    expect(mockCancel).toHaveBeenCalled()
  })

  it('pressing Escape calls cancel', async () => {
    mockState.value = 'listening'
    const wrapper = mountView()
    // Escape handler is bound to window, not component
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(mockCancel).toHaveBeenCalled()
  })

  // ── Ripple animation ─────────────────────────────────────────────────

  it('renders ripple elements in listening state', () => {
    mockState.value = 'listening'
    const wrapper = mountView()
    const ripples = wrapper.findAll('.va-ripple')
    expect(ripples.length).toBeGreaterThanOrEqual(1)
  })
})
