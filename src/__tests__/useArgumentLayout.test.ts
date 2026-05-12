/**
 * Phase 2 TDD — useArgumentLayout composable unit tests.
 *
 * Tests dagre layout with Toulmin rank hints:
 * - All nodes receive positions
 * - In TB direction, claim (target) has higher y than grounds (source)
 */
import { describe, it, expect } from 'vitest'

import { useArgumentLayout } from '../composables/useArgumentLayout'
import type { LayoutNode, LayoutEdge } from '../composables/useArgumentLayout'

function node(id: string, type: LayoutNode['node_type']): LayoutNode {
  return { id, node_type: type, position: null }
}

function edge(id: string, src: string, tgt: string, rel: string): LayoutEdge {
  return { id, source_id: src, target_id: tgt, relation_type: rel }
}

// ── Layout tests ──────────────────────────────────────────────────────────────

describe('useArgumentLayout.autoLayout', () => {
  const { autoLayout } = useArgumentLayout()

  it('assigns positions to all nodes', () => {
    const nodes = [node('n_c', 'claim'), node('n_g', 'grounds')]
    const edges = [edge('e_1', 'n_g', 'n_c', 'supports')]

    const result = autoLayout(nodes, edges)

    expect(result).toHaveLength(2)
    for (const r of result) {
      expect(r.position).toBeDefined()
      expect(typeof r.position!.x).toBe('number')
      expect(typeof r.position!.y).toBe('number')
    }
  })

  it('claim (target) has higher y than grounds (source) in TB layout', () => {
    // In dagre TB: source is above target → grounds.y < claim.y
    const nodes = [node('n_c', 'claim'), node('n_g', 'grounds')]
    const edges = [edge('e_1', 'n_g', 'n_c', 'supports')]

    const result = autoLayout(nodes, edges)

    const claim = result.find(r => r.id === 'n_c')!
    const grounds = result.find(r => r.id === 'n_g')!

    expect(claim.position!.y).toBeGreaterThan(grounds.position!.y)
  })

  it('backing has lower y than warrant (backing → warrant)', () => {
    // backing→warrant edge: backing is source (higher up), warrant is target (lower)
    const nodes = [node('n_w', 'warrant'), node('n_b', 'backing')]
    const edges = [edge('e_1', 'n_b', 'n_w', 'backs')]

    const result = autoLayout(nodes, edges)

    const warrant = result.find(r => r.id === 'n_w')!
    const backing = result.find(r => r.id === 'n_b')!

    expect(backing.position!.y).toBeLessThan(warrant.position!.y)
  })

  it('returns empty array for no nodes', () => {
    const result = autoLayout([], [])
    expect(result).toEqual([])
  })

  it('handles single isolated node (no edges)', () => {
    const nodes = [node('n_solo', 'claim')]
    const result = autoLayout(nodes, [])

    expect(result).toHaveLength(1)
    expect(result[0].position).toBeDefined()
  })

  it('preserves node id in returned positions', () => {
    const nodes = [
      node('n_c1', 'claim'),
      node('n_g1', 'grounds'),
      node('n_w1', 'warrant'),
    ]
    const edges = [
      edge('e_1', 'n_g1', 'n_c1', 'supports'),
      edge('e_2', 'n_w1', 'n_c1', 'warrants'),
    ]

    const result = autoLayout(nodes, edges)

    expect(result).toHaveLength(3)
    const ids = result.map(r => r.id).sort()
    expect(ids).toEqual(['n_c1', 'n_g1', 'n_w1'])
  })

  it('full Toulmin stack: backing above warrant above claim', () => {
    // backing → warrant → claim (via backs + warrants edges)
    // TB layout: backing.y < warrant.y < claim.y
    const nodes = [
      node('n_c', 'claim'),
      node('n_w', 'warrant'),
      node('n_b', 'backing'),
    ]
    const edges = [
      edge('e_1', 'n_b', 'n_w', 'backs'),
      edge('e_2', 'n_w', 'n_c', 'warrants'),
    ]

    const result = autoLayout(nodes, edges)

    const claim = result.find(r => r.id === 'n_c')!
    const warrant = result.find(r => r.id === 'n_w')!
    const backing = result.find(r => r.id === 'n_b')!

    expect(backing.position!.y).toBeLessThan(warrant.position!.y)
    expect(warrant.position!.y).toBeLessThan(claim.position!.y)
  })
})
