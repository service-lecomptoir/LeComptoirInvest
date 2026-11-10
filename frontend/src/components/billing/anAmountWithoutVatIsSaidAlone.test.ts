import { describe, expect, it } from 'vitest'
import { chargesVat, prorataKey } from './planOffer'
import COMPONENT from './PlanChangeOffer.tsx?raw'

/** The card's words in every language of the product. */
const LOCALES = import.meta.glob<{ default: Record<string, Record<string, unknown>> }>('../../i18n/locales/*.json', { eager: true })
const CATALOGUES = Object.values(LOCALES).map(mod => mod.default.planChange as Record<string, unknown>)

/**
 * The owner, 10 Nov 2026: « oui », write the amount ALONE when Alice bills no VAT, keep
 * « TTC » when she does. Alice is under the franchise (CGI art. 293 B): her offer carries
 * `vat_rate: 0` and `vat_mention`, and the card read « TVA 0 % : 0,00 € », « Total TTC »,
 * « Soit 100 € TTC (TVA 0 %) » and a prorata « … TTC ». The word is only true when a
 * positive rate is known; an unknown rate (null) says nothing about the VAT.
 * The same guard in every product, as `PlanChangeOffer.tsx` and `planOffer.ts` are.
 */

describe('an amount Alice bills without VAT is said alone', () => {
  it('says the VAT only where a positive rate is known', () => {
    expect(chargesVat(20)).toBe(true)
    expect(chargesVat(5.5)).toBe(true)
    expect(chargesVat(0)).toBe(false)
    expect(chargesVat(null)).toBe(false)
    expect(chargesVat(undefined)).toBe(false)
  })

  it('words the prorata with « TTC » only under a positive rate', () => {
    expect(prorataKey(12, 20)).toBe('prorataCharge')
    expect(prorataKey(-12, 20)).toBe('prorataCredit')
    expect(prorataKey(12, 0)).toBe('prorataChargeNoTax')
    expect(prorataKey(0, 0)).toBe('prorataChargeNoTax')
    expect(prorataKey(-12, 0)).toBe('prorataCreditNoTax')
    expect(prorataKey(12, null)).toBe('prorataChargeNoTax')
    expect(prorataKey(-12, undefined)).toBe('prorataCreditNoTax')
  })

  it('draws the VAT line, the total and « Soit … TTC » only under a positive rate, the mention otherwise', () => {
    // A known rate is not enough: 0 % drew « TVA 0 % » and « Total TTC ».
    expect(COMPONENT).not.toMatch(/vat_rate !== null/)
    // The bubble of a card and the confirmation window both ask.
    expect(COMPONENT.match(/chargesVat\(/g)?.length ?? 0).toBeGreaterThanOrEqual(2)
    expect(COMPONENT).toMatch(/prorataKey\(/)
    expect(COMPONENT).not.toMatch(/t\('prorata(Charge|Credit)'/)
    // Alice's mention (« TVA non applicable, article 293 B du CGI ») under the price.
    expect(COMPONENT).toMatch(/vat_mention/)
  })

  it('has the prorata without « TTC » in every language of the product', () => {
    expect(CATALOGUES.length).toBeGreaterThan(0)
    for (const words of CATALOGUES) {
      for (const key of ['prorataChargeNoTax', 'prorataCreditNoTax']) {
        expect(words[key]).toContain('{{amount}}')
        expect(words[key]).not.toMatch(/TTC|VAT|IVA|imposto|tax/i)
      }
    }
  })
})
