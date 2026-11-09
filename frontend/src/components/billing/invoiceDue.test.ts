import { describe, expect, it } from 'vitest'
import { invoiceAmount, invoiceDueKind, invoiceDueOf, invoicePeriod } from './invoiceDue'
import SOURCE from './invoiceDue.ts?raw'

/**
 * The owner, 9 Nov 2026: after the billing start, a subscriber paying by transfer, or with
 * no means of payment, had no banner between the invoice e-mail and the suspension. Alice
 * names the invoice still to pay (`invoice_due`); `invoiceDue.ts` is the same file in every
 * product whose banner reads it, and this guard is the same in every product too.
 */
const ALICE = {
  number: 'ABO-2027-0001',
  period_year: 2027,
  period_month: 1,
  left_ttc: 120,
  currency: 'eur',
  due_on: '2027-01-15',
  overdue: false,
}

describe('the invoice still to pay, as Alice names it', () => {
  it('is told while its day is ahead, then as overdue', () => {
    expect(invoiceDueKind(ALICE)).toBe('invoice-due')
    expect(invoiceDueKind({ ...ALICE, overdue: true })).toBe('invoice-overdue')
  })

  it('says nothing when nothing is to pay, for an older Alice, or a malformed answer', () => {
    expect(invoiceDueKind(null)).toBeNull()
    expect(invoiceDueKind(undefined)).toBeNull()
    expect(invoiceDueKind({ ...ALICE, number: '' })).toBeNull()
    expect(invoiceDueKind({ ...ALICE, period_month: 13 })).toBeNull()
    expect(invoiceDueKind({ ...ALICE, left_ttc: '120' })).toBeNull()
    expect(invoiceDueKind({ ...ALICE, due_on: null })).toBeNull()
    expect(invoiceDueKind({ ...ALICE, overdue: undefined })).toBeNull()
  })

  it('names the month in full, without a capital in French, in the reader’s language', () => {
    const invoice = invoiceDueOf(ALICE)!
    expect(invoicePeriod(invoice, 'fr-FR')).toBe('janvier 2027')
    expect(invoicePeriod(invoice, 'en-GB')).toBe('January 2027')
    expect(invoicePeriod(invoice, 'es-ES')).toBe('enero de 2027')
    expect(invoicePeriod(invoice, 'pt-BR')).toBe('janeiro de 2027')
    expect(invoicePeriod({ ...invoice, period_month: 12, period_year: 2026 }, 'fr-FR')).toBe('décembre 2026')
  })

  it('says the amount in the invoice’s currency, with its two decimals', () => {
    const invoice = invoiceDueOf(ALICE)!
    expect(invoice.currency).toBe('EUR')
    expect(invoiceAmount(invoice, 'fr-FR').replace(/\s/g, ' ')).toBe('120,00 €')
    expect(invoiceAmount(invoice, 'en-GB')).toBe('€120.00')
    expect(invoiceAmount({ ...invoice, currency: 'CHF', left_ttc: 1234.5 }, 'fr-FR').replace(/\s/g, ' ')).toBe(
      '1 234,50 CHF',
    )
    expect(invoiceAmount({ ...invoice, currency: 'NOPE' }, 'fr-FR')).toBe('120.00 NOPE')
  })
})

describe('the copy of every product', () => {
  // FNV-1a over the text with LF line ends: a checkout with CRLF reads the same.
  const fingerprint = (text: string): string => {
    let hash = 0x811c9dc5
    for (const char of text.replace(/\r\n/g, '\n')) {
      for (let i = 0; i < char.length; i++) {
        hash ^= char.charCodeAt(i)
        hash = Math.imul(hash, 0x01000193) >>> 0
      }
    }
    return hash.toString(16).padStart(8, '0')
  }

  it('is the shared invoiceDue.ts: change one, change them all', () => {
    expect(fingerprint(SOURCE)).toBe('e5b87206')
  })
})
