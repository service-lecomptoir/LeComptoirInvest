import { describe, expect, it } from 'vitest'
import { BILLING_ROUTES, cardsOf, handedOutKey, offerView, requestablePlans, usageTone, type Offer, type OfferPlan } from './planOffer'
import PAGE from '../../pages/Billing.tsx?raw'
import COMPONENT from './PlanChangeOffer.tsx?raw'

const LOCALES = import.meta.glob<{ default: Record<string, Record<string, unknown>> }>('../../i18n/locales/*.json', { eager: true })

/**
 * The owner, 12 Oct 2026, who did not see the plan change aligned: « je ne le vois toujours pas ».
 * Then, on a bespoke plan: « C'est quoi la différence entre les 2 ? ».
 * ONE card on every « Mon abonnement »: the plan, its quantity, its next payment, the
 * catalogue plans by price, and ONE request. `PlanChangeOffer.tsx` and `planOffer.ts` are
 * the same files in every product; this guard is the same in every product too.
 */

const plan = (name: string, price: number, extra: Partial<OfferPlan> = {}): OfferPlan => ({
  id: name,
  name,
  description: null,
  currency: 'EUR',
  monthly_price: price,
  price_ht: price,
  vat_rate: 20,
  price_ttc: price * 1.2,
  managed_limit: 10,
  overage_allowed: false,
  overage_price: null,
  overage_count: 0,
  overage_monthly: 0,
  is_current: false,
  action: 'change',
  refusal: null,
  ...extra,
})

const OFFER: Offer = {
  managed_count: 3,
  current_kind: 'catalogue',
  self_service: true,
  current: null,
  mode: 'change',
  plans: [],
  can_change: true,
}

describe('the subscription card', () => {
  it('has three faces: the cards, a plan the team hands out, nothing else published', () => {
    const silver = plan('Argent', 12, { is_current: true, action: 'current' })
    expect(offerView({ ...OFFER, current: silver, plans: [silver, plan('Or', 30)] })).toBe('standard')
    expect(offerView({ ...OFFER, current: silver, plans: [silver] })).toBe('empty')
    expect(offerView({ ...OFFER, current_kind: 'beta', self_service: false, plans: [plan('Or', 30)] })).toBe('frozen')
    expect(handedOutKey({ ...OFFER, current_kind: 'bespoke', self_service: false })).toBe('handedOut.bespoke')
  })

  it('ranks the plans by price, the current one at its place', () => {
    const silver = plan('Argent', 12, { is_current: true, action: 'current' })
    const offer = { ...OFFER, current: silver, plans: [silver, plan('Or', 30), plan('Bronze', 8)] }
    expect(cardsOf(offer).map(p => p.name)).toEqual(['Bronze', 'Argent', 'Or'])
    expect(requestablePlans(offer).map(p => p.name)).toEqual(['Bronze', 'Or'])
  })

  it('never repeats a frozen plan as a card: only the catalogue plans, to compare', () => {
    const beta = plan('Bêta-testeur illimité', 0, { is_current: true, action: 'current', managed_limit: null })
    const offer: Offer = { ...OFFER, current_kind: 'beta', self_service: false, mode: 'request', current: beta, plans: [plan('PME', 49), plan('Essentiel', 19)] }
    expect(cardsOf(offer).map(p => p.name)).toEqual(['Essentiel', 'PME'])
  })

  it('draws no bar without a ceiling, orange at the ceiling, red only beyond', () => {
    expect(usageTone(12, null)).toBe('none')
    expect(usageTone(2, 2)).toBe('full')
    expect(usageTone(3, 2)).toBe('over')
    expect(usageTone(1, 2)).toBe('ok')
  })

  it('has one request window and one way in, never a name cut, never a native box', () => {
    expect(COMPONENT).not.toMatch(/window\.(confirm|alert|prompt)\(/)
    expect(COMPONENT).not.toMatch(/truncate/)
    expect(COMPONENT.match(/<AskChange\b/g)).toHaveLength(1)
    expect(COMPONENT).not.toMatch(/handedOutHelp|amber-50/)
  })

  it('is the page’s only plan card, fed by Alice’s offer through this server', () => {
    expect(PAGE.match(/<PlanChangeOffer\b/g)).toHaveLength(1)
    expect(PAGE).not.toMatch(/billing\.currentPlan|billing\.renewsOn|billing\.offers'/)
    expect(Object.values(BILLING_ROUTES).every(route => route.startsWith('/billing/'))).toBe(true)
  })

  it('speaks every language of the product, with the French typography', () => {
    const words = Object.fromEntries(
      Object.entries(LOCALES).map(([file, mod]) => [file.replace(/^.*\//, '').replace('.json', ''), mod.default.planChange]),
    )
    const keys = (lang: string) => Object.keys(words[lang] ?? {}).sort()
    expect(keys('fr').length).toBeGreaterThan(40)
    for (const lang of Object.keys(words)) expect(keys(lang)).toEqual(keys('fr'))
    for (const key of ['currentLabel', 'changePlan', 'requestButton', 'customButton', 'ask', 'current', 'empty']) {
      expect(words.fr[key]).toBeTruthy()
    }
    const text = JSON.stringify(words.fr)
    expect(text).not.toMatch(/[–—]/)
    expect(text).not.toMatch(/ [:;?!]/)
  })
})
