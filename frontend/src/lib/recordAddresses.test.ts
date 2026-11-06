// No address of a record shows a technical identifier: the rule for every screen to come.
import { describe, expect, it } from 'vitest'
import ROUTER from '../router.tsx?raw'

/**
 * The owner, 6 Nov 2026: `/funds/0ad7e24e-…` will never be an address. Invest has no record
 * with a screen of its own today (flat screens). The day one arrives, it takes its letters
 * in Alice's catalogue (LeComptoirAlice/docs/SHORT_REFERENCES.md), carries a short reference
 * (`F-0001`) drawn by the database, and its screen reads its address through
 * `useRecordParam`, as in Immo. Until then, a route parameter that is not the secret token
 * of a public link fails here.
 */
const NOT_A_RECORD = new Set(['token'])

const routePaths = (): string[] => [...ROUTER.matchAll(/path:\s*'([^']+)'/g)].map(m => m[1])

describe('record addresses', () => {
  it('the router is read (a guard over an empty set passes for ever)', () => {
    expect(routePaths().length).toBeGreaterThan(10)
  })

  it('no route parameter names a record: a record gets a short reference first', () => {
    const offenders = routePaths()
      .filter(path => path.includes(':'))
      .filter(path => ![...path.matchAll(/:([A-Za-z]+)/g)].every(m => NOT_A_RECORD.has(m[1])))
    expect(offenders).toEqual([])
  })
})
