import { describe, expect, it } from 'vitest'
import landing from './Landing.tsx?raw'
import pricing from './Pricing.tsx?raw'
import router from '../router.tsx?raw'
import fr from '../i18n/locales/fr.json'
import en from '../i18n/locales/en.json'

/**
 * The public home page at `/`, laid out as Le Comptoir Immo's: four sections a visitor
 * reaches from the header, the plans the console sells, and questions answered from the
 * code.
 *
 * 🔴 WHAT WOULD BREAK IT WITHOUT A SOUND: an anchor renamed on one side only (the header
 * scrolls nowhere), the demo line shown under a free plan or a quotation (a promise the
 * console does not make), a question added in French only, or the visitor sent to the
 * sign-in again instead of the page.
 */
const LOCALES: Record<string, Record<string, any>> = { fr, en }
const ANCHORS = ['how-it-works', 'features', 'pricing', 'faq']

const flatten = (obj: Record<string, unknown>, prefix = ''): string[] =>
  Object.entries(obj).flatMap(([k, v]) =>
    v && typeof v === 'object' ? flatten(v as Record<string, unknown>, `${prefix}${k}.`) : [`${prefix}${k}`],
  )

describe('the public page', () => {
  it('is what a visitor gets at /, and a signed-in reader still gets their home', () => {
    expect(router).toContain("if (location.pathname === '/') return <Landing />")
    expect(router).toContain("{ path: '/', element: <Home /> }")
  })

  it('has the four sections, each reached from the header', () => {
    for (const anchor of ANCHORS) {
      expect(landing, `section #${anchor}`).toContain(`id="${anchor}"`)
      expect(landing, `link to #${anchor}`).toContain(`href: '#${anchor}'`)
    }
  })

  it('draws the same plans as the pricing page, and the demo under a priced plan only', () => {
    expect(landing).toContain('<PlanOffer')
    // The catalogue only, and the demo only where there is a price to try: never on a
    // quotation, never on a free plan, and never with a number of days.
    expect(pricing).toContain('.filter((plan) => !plan.sur_devis)')
    // The rule is the sign-up's (`showsFreeDemo`: a priced catalogue plan), read by both.
    expect(pricing).toMatch(/\{showsFreeDemo\(plan\) && \(\s*<p[^>]*>\{t\('pricing\.freeDemo'\)\}/)
    for (const [lang, catalogue] of Object.entries(LOCALES)) {
      expect(catalogue.pricing.freeDemo, lang).toBeTruthy()
      expect(catalogue.pricing.freeDemo, `${lang}: no number of days`).not.toMatch(/\d/)
    }
  })

  it('answers between six and ten questions, the same ones in every language', () => {
    const keys = [...(/const FAQ_KEYS = \[([\s\S]*?)\]/.exec(landing)?.[1] ?? '').matchAll(/'([^']+)'/g)].map(
      (m) => m[1],
    )
    expect(keys.length).toBeGreaterThanOrEqual(6)
    expect(keys.length).toBeLessThanOrEqual(10)
    for (const [lang, catalogue] of Object.entries(LOCALES)) {
      const items = catalogue.landing.faq.items as Record<string, { q: string; a: string }>
      expect(Object.keys(items).sort(), lang).toEqual([...keys].sort())
      for (const key of keys) {
        expect(items[key].q?.trim(), `${lang}: ${key}.q`).toBeTruthy()
        expect(items[key].a?.trim(), `${lang}: ${key}.a`).toBeTruthy()
      }
    }
  })

  it('has the same landing keys in every language', () => {
    const reference = flatten(fr.landing).sort()
    expect(reference.length).toBeGreaterThan(20)
    for (const [lang, catalogue] of Object.entries(LOCALES)) {
      expect(flatten(catalogue.landing).sort(), lang).toEqual(reference)
    }
  })

  it('draws its features from the guide, which a guard ties to the router', () => {
    expect(landing).toContain("from '@/lib/guide'")
    expect(landing).toContain('guide.cards.${card.id}.what')
  })
})
