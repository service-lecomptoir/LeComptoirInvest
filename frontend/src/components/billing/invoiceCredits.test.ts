import { describe, expect, it } from 'vitest'
import { creditsOf, nothingLeftToPay } from './invoiceCredits'
import SOURCE from './invoiceCredits.ts?raw'

/**
 * The owner, 6 Nov 2026: « les avoirs visibles dans "Mon abonnement" des produits ».
 * `invoiceCredits.ts` is the same file in every product that lists its invoices; this
 * guard is the same in every product too.
 */

const note = (number: string, amount: string, extra: Record<string, unknown> = {}) => ({
  id: `id-${number}`,
  number,
  invoice_family: 'subscription',
  issued_on: '2026-11-06',
  amount_ttc: amount,
  reason: 'Geste commercial accordé.',
  currency: 'EUR',
  ...extra,
})

describe('the credit notes of an invoice', () => {
  it('shows nothing on an invoice without a credit note', () => {
    expect(creditsOf({ credit_notes: [], credit_state: 'none' })).toEqual({ notes: [], state: 'none' })
  })

  it('reads a partial credit note: its number, day, amount and reason', () => {
    const credits = creditsOf({ credit_notes: [note('AV-2026-00001', '6.00')], credit_state: 'partial' })
    expect(credits.state).toBe('partial')
    expect(credits.notes).toEqual([
      {
        id: 'id-AV-2026-00001',
        number: 'AV-2026-00001',
        issuedOn: '2026-11-06',
        amount: 6,
        reason: 'Geste commercial accordé.',
        currency: 'EUR',
      },
    ])
    expect(nothingLeftToPay(credits)).toBe(false)
  })

  it('reads a total credit note: nothing is left to pay', () => {
    const credits = creditsOf({
      credit_notes: [note('AV-2026-00001', '6.00'), note('AV-2026-00002', '30.00')],
      credit_state: 'total',
    })
    expect(credits.state).toBe('total')
    expect(credits.notes.map((n) => n.amount)).toEqual([6, 30])
    expect(nothingLeftToPay(credits)).toBe(true)
  })

  it('reads an answer of an older Alice, without the fields, as before', () => {
    expect(creditsOf({})).toEqual({ notes: [], state: 'none' })
    expect(creditsOf({ credit_notes: null, credit_state: undefined })).toEqual({ notes: [], state: 'none' })
  })

  it('drops what it cannot show, and never shows a badge without a credit note', () => {
    const credits = creditsOf({
      credit_notes: [null, 'AV', { id: 'x' }, note('AV-2026-00003', 'n/a'), note('AV-2026-00004', '1.50', { currency: 'brl' })],
      credit_state: 'total',
    })
    expect(credits.notes.map((n) => [n.number, n.currency])).toEqual([['AV-2026-00004', 'BRL']])
    expect(creditsOf({ credit_notes: [], credit_state: 'total' }).state).toBe('none')
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

  it('is the shared invoiceCredits.ts: change one, change them all', () => {
    expect(fingerprint(SOURCE)).toBe('7c02afb2')
  })
})
