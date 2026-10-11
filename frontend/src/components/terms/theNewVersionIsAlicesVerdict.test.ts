import { describe, expect, it } from 'vitest'
import SOURCE from './AcceptedTerms.tsx?raw'

/**
 * The owner, 11 Oct 2026, on a « Mon abonnement » page: « Version 2026-10, acceptée le 10 oct.
 * 2026 », then « Une nouvelle version 2026-09 est en vigueur depuis le 30 sept. 2026 ». A
 * different version is not a later one. Alice orders the versions by effective date and says
 * it in `pending`; the line reads her verdict, never a string comparison.
 */
describe('the « nouvelle version » line', () => {
  it('reads Alice’s verdict, never `version !==`', () => {
    expect(SOURCE).toContain('.pending')
    expect(SOURCE).not.toMatch(/\.version\s*!==/)
  })
})
