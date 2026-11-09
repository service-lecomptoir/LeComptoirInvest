/**
 * An ended licence settles ONE invoice, never subscribes again by paying it (the owner,
 * 9 Nov 2026).
 *
 * The subscriber of an ended licence keeps « Mon abonnement ». « Payer par carte » on an
 * invoice still due goes through `POST /billing/invoices/{id}/pay` (Alice's `pay-invoice`:
 * that invoice alone, or the open invoice of a running subscription), never the Checkout of
 * the plan, which would subscribe again, nor the portal. Licences active or suspended keep
 * their way out.
 */
import { describe, expect, it } from 'vitest'
import PAGE from '../../pages/Billing.tsx?raw'
import API from '../../api/index.ts?raw'

describe('an ended licence pays one invoice', () => {
  it('has its own call, on the invoice', () => {
    expect(API).toContain('payInvoice: (id: string) =>')
    expect(API).toContain('`/billing/invoices/${id}/pay`')
  })

  it('is what « Régler » does on an invoice, of an ended licence or any other (the recipe, 9 Nov 2026)', () => {
    expect(PAGE).toContain('onClick={() => payInvoice(invoice)}')
    expect(PAGE).toContain('billingApi.payInvoice(invoice.id)')
  })
})
