import { describe, expect, it } from 'vitest'
import { money } from '@/lib/format'
import PAGE from '../../pages/Billing.tsx?raw'

/**
 * 8 Nov 2026 (Le Comptoir Immo's fix of 7 Nov, carried to every product): « Mon abonnement »
 * wrote each invoice in the currency of the payment methods, not in the one Alice billed it
 * in. Alice now serves each invoice's own `currency` (`/internal/invoices/{user_id}`), and the
 * page writes the amount in it through the one money formatter; an older Alice that names
 * none billed in euros only. The credit notes already kept theirs.
 */
describe('a subscription invoice is written in its own currency', () => {
  it("reads the invoice's currency, never the payment methods'", () => {
    expect(PAGE).toContain("return money(amount, invoice.currency || 'EUR')")
    expect(PAGE).toContain('<Td right>{invoiceAmountSaid(invoice)}</Td>')
    expect(PAGE).not.toContain('methods?.currency')
  })

  it('keeps the credit notes in theirs', () => {
    expect(PAGE).toContain('money(note.amount, note.currency)')
  })

  it('writes the amount in that currency, with its own minor unit', () => {
    expect(money('34.80', 'CHF')).toContain('CHF')
    expect(money('34.80', 'CHF')).not.toContain('€')
    expect(money('34.80', 'EUR')).toContain('€')
    expect(money(4500, 'XOF')).not.toMatch(/[.,]00/)
  })
})
