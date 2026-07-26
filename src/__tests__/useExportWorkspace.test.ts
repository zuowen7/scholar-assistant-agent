import { describe, expect, it } from 'vitest'
import { analyzeExportReadiness, humanizeExportError } from '../composables/useExportWorkspace'

describe('useExportWorkspace helpers', () => {
  it('reports only evidence found in the current markdown', () => {
    const checks = analyzeExportReadiness(
      '# Paper\n\n## 摘要\n\nText {{cite:key}}.\n\n![](figure.png)',
    )
    expect(checks.find((check) => check.id === 'title')?.level).toBe('pass')
    expect(checks.find((check) => check.id === 'abstract')?.level).toBe('pass')
    expect(checks.find((check) => check.id === 'citations')?.level).toBe('error')
    expect(checks.find((check) => check.id === 'image-alt')?.label).toContain('1')
  })

  it('turns missing asset compiler output into an actionable message', () => {
    const result = humanizeExportError("LaTeX error: file 'figure_3.png' not found")
    expect(result.summary).toContain('figure_3.png')
    expect(result.actionable).toBe(true)
  })

  it('distinguishes a missing compiler from a document defect', () => {
    const result = humanizeExportError('Tectonic LaTeX compiler unavailable')
    expect(result.summary).toContain('编译器')
    expect(result.actionable).toBe(false)
  })
})
