import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useToast, toasts } from '../composables/useToast'

describe('useToast', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    // Clear shared singleton state between tests
    toasts.value = []
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('adds a toast with correct level and message', () => {
    const { success } = useToast()
    success('Operation completed')

    expect(toasts.value).toHaveLength(1)
    expect(toasts.value[0].level).toBe('success')
    expect(toasts.value[0].message).toBe('Operation completed')
    expect(toasts.value[0].id).toBeTypeOf('number')
  })

  it('adds toasts of all levels', () => {
    const { success, warn, danger, info } = useToast()

    success('ok')
    warn('watch out')
    danger('error')
    info('note')

    expect(toasts.value).toHaveLength(4)
    expect(toasts.value.map(t => t.level)).toEqual(['success', 'warn', 'danger', 'info'])
  })

  it('dismisses a toast by id', () => {
    const { success, dismiss } = useToast()
    success('first')
    success('second')

    const firstId = toasts.value[0].id
    dismiss(firstId)

    expect(toasts.value).toHaveLength(1)
    expect(toasts.value[0].message).toBe('second')
  })

  it('auto-dismisses after configured duration', () => {
    const { success } = useToast()
    success('Will disappear', 1000)

    expect(toasts.value).toHaveLength(1)

    vi.advanceTimersByTime(1000)

    expect(toasts.value).toHaveLength(0)
  })

  it('does not auto-dismiss when duration is 0', () => {
    const { info } = useToast()
    info('Sticky toast', 0)

    vi.advanceTimersByTime(10000)

    expect(toasts.value).toHaveLength(1)
    expect(toasts.value[0].message).toBe('Sticky toast')
  })

  it('returns unique ids across multiple calls', () => {
    const { success } = useToast()
    success('a')
    success('b')
    success('c')

    const ids = toasts.value.map(t => t.id)
    const unique = new Set(ids)
    expect(unique.size).toBe(3)
  })

  it('show() method with custom level', () => {
    const { show } = useToast()
    show('info', 'Custom message', 2000)

    expect(toasts.value[0].level).toBe('info')
    expect(toasts.value[0].message).toBe('Custom message')
    expect(toasts.value[0].duration).toBe(2000)
  })
})
