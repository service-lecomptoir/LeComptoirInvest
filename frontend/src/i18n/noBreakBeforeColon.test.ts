import { describe, expect, it } from 'vitest'

import fr from './locales/fr.json'

/**
 * French puts a NON-BREAKING space before a colon. With an ordinary space the line may
 * break just before it: « Paiement déclaré » on one line, « : à valider » on the next
 * (the manager, 10 Sept 2026). The rule is typographic and holds for every label, so
 * it is checked on every label rather than fixed where it was seen.
 */
const offenders: string[] = []
const walk = (node: unknown, path: string) => {
  if (typeof node === 'string') {
    if (/\S :/.test(node)) offenders.push(`${path}: ${node.slice(0, 60)}`)
  } else if (node && typeof node === 'object') {
    for (const [k, v] of Object.entries(node as Record<string, unknown>)) walk(v, path ? `${path}.${k}` : k)
  }
}

describe('French labels', () => {
  it('never put a breaking space before a colon', () => {
    walk(fr, '')
    expect(offenders, 'use a non-breaking space (U+00A0) before the colon').toEqual([])
  })
})
