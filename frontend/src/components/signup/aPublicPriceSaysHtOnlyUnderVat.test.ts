import { describe, expect, it } from 'vitest'

import fr from '@/i18n/locales/fr.json'
import en from '@/i18n/locales/en.json'
import PRICING from '@/pages/Pricing.tsx?raw'
import SIGNUP_FORM from './SignupForm.tsx?raw'

/**
 * « Enlève HT partout » (the owner, 10 Nov 2026). Alice bills under the VAT franchise (CGI
 * art. 293 B): a subscription price is written ALONE, never « Hors taxes, TVA 20 % en sus »
 * nor « Le prix s'entend hors taxes ». The day the console turns the regime to « liable »,
 * the words come back by themselves: the public catalogue Alice serves carries `vat_rate`
 * (0 under the franchise), the server relays it, and the pricing cards and the sign-up say
 * the tax only beside a positive rate (`chargesVat`, `taxWordKey`), nothing when it is missing.
 */

const TAX_WORDS = /hors tax|\bHT\b|TTC|en sus|TVA|\btax|VAT/i

describe('a public subscription price', () => {
  it('has the pricing card say the tax only under a positive rate, at Alice\'s rate', () => {
    expect(PRICING).toMatch(/chargesVat\(plan\.vat_rate\)/)
    expect(PRICING).toMatch(/t\('pricing\.excludingTax', \{ rate: plan\.vat_rate \}\)/)
    expect(PRICING).not.toMatch(/rate: plan\.tva_rate/)
  })

  it('has the sign-up hint follow the rate of the plans', () => {
    expect(SIGNUP_FORM).toMatch(/taxWordKey\('signup\.planHint', /)
    expect(SIGNUP_FORM).not.toMatch(/t\('signup\.planHint'\)/)
  })

  it('has the hint without any tax in both languages', () => {
    for (const [lang, cat] of [['fr', fr], ['en', en]] as const) {
      const words = cat.signup.planHintNoTax
      expect(words, lang).toBeTruthy()
      expect(words, lang).not.toMatch(TAX_WORDS)
    }
  })
})
