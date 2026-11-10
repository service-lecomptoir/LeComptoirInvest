import { describe, expect, it } from 'vitest'
import PAGE from './Billing.tsx?raw'
import TYPES from '../types/index.ts?raw'

const LOCALES = import.meta.glob<{ default: Record<string, Record<string, unknown>> }>('../i18n/locales/*.json', {
  eager: true,
})

/** The invoice rows of the page, where « Régler » lives. */
const ROWS = PAGE.slice(PAGE.indexOf('invoices.map('))

/**
 * The owner's recipe of 9 Nov 2026 on « Mon abonnement » (« tous les cas doivent être
 * gérés »), measured on this page before it was corrected:
 *
 * 1. « Changer de moyen de paiement » opened Alice's Checkout for a subscriber: a second
 *    Stripe subscription. A subscriber gets « Gérer mon abonnement » (the portal) alone,
 *    and Alice's refusal of that Checkout (409 `already_subscribed`) is said in clear;
 * 2. « Régler » on an issued invoice opened the plan's Checkout for whoever held no
 *    subscription: it subscribed again and charged a proration. It pays THAT invoice
 *    (Alice's `pay-invoice`), for every licence;
 * 3. a payer by transfer whose month is paid, and a demonstration account, read
 *    « Paiement à mettre en place », « Payer maintenant » and the bank details. Immo's rule
 *    (`owesCurrent`): the month is owed only when billed, not paid, not a demo, not held by
 *    a subscription, not free.
 */
describe('« Mon abonnement » offers what is owed, and only that', () => {
  it('draws the Checkout button only for whoever holds no subscription', () => {
    // The rule is the shared billedPeriod.ts (its own test holds the cases): no Checkout for
    // a subscriber, a month paid or a demonstration account; a closed licence subscribes again.
    expect(PAGE).toContain('const payShown = planCheckoutOf(held) !== null')
    expect(PAGE).toMatch(/\{payShown && \(\s*<Button/)
    expect(PAGE).not.toContain("t('billing.updateCard')")
    expect(PAGE).toContain("t('billing.openPortal')")
  })

  it('settles an invoice alone, never through the plan Checkout nor the portal', () => {
    expect(ROWS).toContain('onClick={() => payInvoice(invoice)}')
    expect(ROWS).not.toContain('goToPayment(')
    expect(ROWS).not.toContain('openPortal')
    expect(ROWS).toContain('owes(invoice) && !isDemo')
  })

  it('reads the month paid and the demonstration account, as Immo does', () => {
    expect(TYPES).toMatch(/current_period_paid\?: boolean/)
    expect(PAGE).toContain('const held: HeldPlan = { status, ended: !!current?.ended, price: status?.monthly_price }')
    expect(PAGE).toContain('const transferShown = transferOffered(held, invoices.some(owes))')
    expect(PAGE).toMatch(/badge === 'up-to-date' \? \(\s*<Badge variant="green">\{t\('billing\.upToDate'\)\}/)
    expect(PAGE).toMatch(/badge === 'demo' \? \(\s*<Badge variant="gray">\{t\('billing\.demoAccount'\)\}/)
  })

  it('has its words in every language, each written for its reader', () => {
    const languages = Object.entries(LOCALES)
    expect(languages.length).toBe(2)
    const french = languages.find(([file]) => file.endsWith('/fr.json'))![1].default.billing
    for (const [file, { default: catalogue }] of languages) {
      for (const key of ['upToDate', 'demoAccount', 'invoiceSettle']) {
        const said = catalogue.billing[key]
        expect(typeof said === 'string' && said.length > 0, `billing.${key} in ${file}`).toBe(true)
        if (!file.endsWith('/fr.json') && key !== 'invoiceSettle') expect(said, `${file} copies the French`).not.toBe(french[key])
      }
      // The words of what was removed go with it.
      expect(catalogue.billing.updateCard, `${file}: billing.updateCard`).toBeUndefined()
      expect(catalogue.billing.invoicePayByCard, `${file}: billing.invoicePayByCard`).toBeUndefined()
    }
  })
})
