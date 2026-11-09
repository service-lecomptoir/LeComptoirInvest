import { describe, expect, it } from 'vitest'
import { subscriptionBannerOf } from './subscriptionBanner'
import BANNER from '../components/layout/SubscriptionBanner.tsx?raw'
import fr from '../i18n/locales/fr.json'

/**
 * The owner, 9 Nov 2026: after the billing start, a subscriber paying by transfer, or with no
 * means of payment, had no banner between the invoice e-mail and the suspension. Alice names
 * the invoice still to pay (`invoice_due`, components/billing/invoiceDue.ts); the holder is
 * told, blue while its day is ahead, amber once passed.
 */
const TODAY = '2026-11-09'
const started = {
  managed: true,
  unavailable: false,
  is_holder: true,
  plan_name: 'Essentiel',
  monthly_price: 19,
  is_blocked: false,
  suspended: false,
  ended: false,
  terminated: false,
  billing_starts_on: '2026-11-01',
  has_payment_method: true,
  payment_failed_on: null,
  suspension_on: null,
}
const invoice = {
  number: 'ABO-2026-0042',
  period_year: 2026,
  period_month: 11,
  left_ttc: 120,
  currency: 'EUR',
  due_on: '2026-11-25',
  overdue: false,
}
const decide = (info: object, isDemo: boolean | null = false) => subscriptionBannerOf(info as never, isDemo, TODAY)

describe('the invoice still to pay', () => {
  it('is told to the holder, blue while its day is ahead, amber once passed', () => {
    expect(decide({ ...started, invoice_due: invoice })).toBe('invoice-due')
    expect(decide({ ...started, invoice_due: { ...invoice, overdue: true } })).toBe('invoice-overdue')
  })

  it('never to the team, and nothing when Alice names none', () => {
    expect(decide({ ...started, is_holder: false, invoice_due: invoice })).toBeNull()
    expect(decide({ ...started, invoice_due: null })).toBeNull()
  })

  it('a suspension, an ended subscription and a refused debit go first', () => {
    const owed = { ...started, invoice_due: { ...invoice, overdue: true } }
    expect(decide({ ...owed, is_blocked: true, suspended: true })).toBe('suspended')
    expect(decide({ ...owed, is_blocked: true, ended: true, terminated: true })).toBe('ended')
    expect(decide({ ...owed, payment_failed_on: '2026-11-02' })).toBe('payment-failed')
  })

  it('« devient payant » never stands beside it', () => {
    const before = { ...started, billing_starts_on: '2027-01-01', has_payment_method: false }
    expect(decide({ ...before, invoice_due: invoice }, null)).toBe('invoice-due')
  })

  it('the banner says it in the owner’s words, closable only while its day is ahead', () => {
    const words = (fr as { subscriptionBanner: Record<string, string> }).subscriptionBanner
    expect(words.invoiceDue).toBe('Votre facture de {{period}} ({{amount}}) est à régler avant le {{date}}.')
    expect(words.invoiceOverdue).toBe('Votre facture de {{period}} ({{amount}}) n\'est pas réglée : elle était due le {{date}}.')
    expect(BANNER).toContain("t('subscriptionBanner.invoiceOverdue', owed)")
    expect(BANNER).toContain("(kind === 'billing-starts' || kind === 'invoice-due') && (")
    expect(BANNER).toContain('invoiceClosedForTheSession(invoice.number)')
  })
})
