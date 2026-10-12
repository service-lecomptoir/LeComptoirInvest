import { describe, expect, it } from 'vitest'
import { handedOutKey, type Offer } from './planOffer'
import PAGE from '../../pages/Billing.tsx?raw'
import COMPONENT from './PlanChangeOffer.tsx?raw'
import ROUTES from './planOffer.ts?raw'
import fr from '../../i18n/locales/fr.json'
import en from '../../i18n/locales/en.json'

/**
 * The owner, 11 Oct 2026: « Je ne vois pas la possibilité de changer d'offre comme pour
 * Immo [...] faudra les aligner. » The plans are Alice's offer, drawn as cards with their
 * VAT and their refusals, changed through a confirmation, or asked of the team.
 */

const OFFER: Offer = {
  managed_count: 3,
  current_kind: 'catalogue',
  self_service: true,
  current: null,
  mode: 'change',
  plans: [],
  can_change: true,
}

describe('the plan change', () => {
  it('asks the team for a plan it hands out, and says why', () => {
    expect(handedOutKey({ ...OFFER, current_kind: 'beta', self_service: false })).toBe('planChange.handedOut.beta')
    expect(handedOutKey({ ...OFFER, current_kind: 'bespoke', self_service: false })).toBe('planChange.handedOut.bespoke')
    expect(handedOutKey(OFFER)).toBeNull()
  })

  it('is the page’s, from Alice’s offer, through this server', () => {
    expect(PAGE).toContain('<PlanChangeOffer')
    for (const route of ['/billing/offer', '/billing/change-plan-preview', '/billing/change-plan', '/billing/checkout', '/billing/change-request']) {
      expect(ROUTES).toContain(`'${route}'`)
    }
    // Never a native dialog; the house's dialog does not close on an outside click.
    expect(COMPONENT).not.toMatch(/window\.(confirm|alert|prompt)\(/)
  })

  it('speaks every language of the product, with the French typography', () => {
    const words = (fr as Record<string, Record<string, unknown>>).planChange
    expect(Object.keys(words).sort()).toEqual(Object.keys((en as Record<string, Record<string, unknown>>).planChange).sort())
    const text = JSON.stringify(words)
    expect(text).not.toMatch(/[\u2013\u2014]/)
    expect(text).not.toMatch(/ [:;?!]/)
  })
})
