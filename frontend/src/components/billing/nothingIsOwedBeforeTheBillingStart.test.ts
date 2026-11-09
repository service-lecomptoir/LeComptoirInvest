/**
 * Before the billing start, nothing is owed (the owner, 9 Nov 2026).
 *
 * In Immo, an account out of the demonstration, with no means of payment, read « À régler »,
 * « Payer mon abonnement » and the transfer details on 9 November, when the first invoice is
 * on 1 January 2027. Measured on origin/main 35eefce: Invest drew no « À régler » for the
 * month, but its plan card said « Paiement à mettre en place », its card button « Payer
 * maintenant » (« Paiement immédiat »), and the bank details with « J'ai fait le virement »
 * stood there for a month nobody owes. Alice now says whether the month is billed
 * (`current_period_billed`): the page reads it.
 */
import { describe, expect, it } from 'vitest'
import PAGE from '../../pages/Billing.tsx?raw'
import TYPES from '../../types/index.ts?raw'
import fr from '../../i18n/locales/fr.json'
import en from '../../i18n/locales/en.json'

describe('« Mon abonnement » before the billing start', () => {
  it('reads from Alice whether the month is billed', () => {
    expect(TYPES).toContain('current_period_billed?: boolean')
    expect(PAGE).toContain("from '@/components/billing/billedPeriod'")
    expect(PAGE).toMatch(/const startsLater =[^;]*!periodBilled\(status\)/)
  })

  it('says « Actif » before the start', () => {
    expect(PAGE).toMatch(/status\?\.has_subscription \|\| startsLater \? \(\s*<Badge variant="green">\{t\('billing\.active'\)\}<\/Badge>/)
  })

  it('offers to add a means of payment, not to pay now, before the start', () => {
    expect(PAGE).toContain("planPayment(status) === 'add-method'")
    expect(PAGE).toContain("t('billing.addMethod')")
    expect(PAGE).toContain("t('billing.nothingChargedBefore'")
    expect(fr.billing.addMethod).toBe('Ajouter un moyen de paiement')
    expect(en.billing.addMethod).toBe('Add a payment method')
    expect(fr.billing.nothingChargedBefore).toContain('{{day}}')
    expect(en.billing.nothingChargedBefore).toContain('{{day}}')
  })

  it('shows no transfer to declare for a month not billed, unless an issued invoice is owed', () => {
    expect(PAGE).toContain('const transferShown = periodBilled(status) || invoices.some(owes)')
    expect(PAGE).toContain('methods?.transfer_enabled && methods.transfer && transferShown && (')
  })
})
