import { describe, expect, it } from 'vitest'
import { readFileSync, readdirSync } from 'node:fs'
import { extname, join, relative } from 'node:path'

const srcRoot = join(process.cwd(), 'src')
const sourceExtensions = new Set(['.css', '.ts', '.vue'])

function sourceFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const path = join(directory, entry.name)
    if (entry.isDirectory()) return sourceFiles(path)
    return sourceExtensions.has(extname(entry.name)) ? [path] : []
  })
}

const files = sourceFiles(srcRoot)
const sources = files.map(path => ({ path, text: readFileSync(path, 'utf8') }))

function matches(pattern: RegExp) {
  return sources.flatMap(source => [...source.text.matchAll(pattern)].map(match => ({
    name: match[1],
    file: relative(process.cwd(), source.path).replaceAll('\\', '/'),
  })))
}

describe('design token contract', () => {
  it('does not reference undeclared static custom properties', () => {
    const definitions = new Set(matches(/--([A-Za-z0-9_-]+)\s*:/g).map(match => match.name))
    const allowedRuntimeTokens = new Set(['i', 'read-ff', 'read-fs', 'read-lh', 'read-trans-color'])
    const undefinedTokens = matches(/var\(--([A-Za-z0-9_-]+)/g)
      .filter(match => !definitions.has(match.name) && !allowedRuntimeTokens.has(match.name))
      .map(match => `--${match.name} (${match.file})`)

    expect([...new Set(undefinedTokens)].sort()).toEqual([])
  })

  it('keeps feature code on the canonical token vocabulary', () => {
    const deprecatedAliases = new Set([
      'c-error', 'c-warning', 'c-text', 'c-text-secondary', 'c-text-muted',
      'c-brand-red', 'c-panel-bg', 'c-nav-bg', 'c-brand', 'ease',
    ])
    const legacyReferences = matches(/var\(--([A-Za-z0-9_-]+)/g)
      .filter(match => deprecatedAliases.has(match.name))
      .map(match => `--${match.name} (${match.file})`)

    expect([...new Set(legacyReferences)].sort()).toEqual([])
  })

  it('does not hide ReviewerThread palette regressions behind hex fallbacks', () => {
    const reviewer = readFileSync(join(srcRoot, 'components/argument/ReviewerThread.vue'), 'utf8')
    expect(reviewer).not.toMatch(/var\(--c-[A-Za-z0-9_-]+\s*,\s*#[0-9a-fA-F]{3,8}\)/)
  })
})
