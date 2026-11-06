/**
 * The credit notes of a subscription invoice, as Alice serves them (the owner, 6 Nov 2026:
 * « les avoirs visibles dans "Mon abonnement" des produits »).
 *
 * Alice lists each invoice with its `number`, its `credit_notes` and its `credit_state`
 * (LeComptoirAlice, docs/COMMISSION_INVOICES.md § 11). An answer from an older Alice has
 * none of them: the invoice then reads as before, with no credit note and no badge.
 *
 * ⚠️ THE SAME FILE IN EVERY PRODUCT THAT LISTS ITS INVOICES (Immo, Séjour, Market, Invest,
 * PDF, Compta, Syndic, BTP), beside planOffer.ts, under the fingerprint of
 * invoiceCredits.test.ts: change one, change them all, and the fingerprint.
 */

/** One credit note, as a screen shows it. Its amount is positive: a note takes off. */
export interface InvoiceCreditNote {
  id: string
  /** « AV-YYYY-NNNNN ». */
  number: string
  /** Day of issue, `YYYY-MM-DD`. */
  issuedOn: string
  /** Amount including tax. */
  amount: number
  reason: string
  /** ISO 4217 code, upper case. */
  currency: string
}

/** What the credit notes left of the invoice: nothing taken off, a part, or all of it. */
export type InvoiceCreditState = 'none' | 'partial' | 'total'

export interface InvoiceCredits {
  notes: InvoiceCreditNote[]
  state: InvoiceCreditState
}

/** The fields of an invoice this file reads, all optional: an older Alice sends none. */
export interface InvoiceCreditFields {
  credit_notes?: unknown
  credit_state?: unknown
}

const text = (value: unknown): string => (typeof value === 'string' ? value.trim() : '')

function noteOf(raw: unknown): InvoiceCreditNote | null {
  if (!raw || typeof raw !== 'object') return null
  const note = raw as Record<string, unknown>
  const id = text(note.id)
  const number = text(note.number)
  // Alice sends her amounts as decimal strings (« 6.00 »).
  const amount = Number(note.amount_ttc)
  if (!id || !number || !Number.isFinite(amount)) return null
  return {
    id,
    number,
    issuedOn: text(note.issued_on),
    amount,
    reason: text(note.reason),
    currency: text(note.currency).toUpperCase() || 'EUR',
  }
}

/** What an invoice's credit notes say of it; nothing when Alice did not say. */
export function creditsOf(invoice: InvoiceCreditFields): InvoiceCredits {
  const notes = Array.isArray(invoice.credit_notes)
    ? invoice.credit_notes.map(noteOf).filter((n): n is InvoiceCreditNote => n !== null)
    : []
  // Alice decides the state (she compares the notes with the invoice); without a note to
  // show there is no badge, whatever the state says.
  const state: InvoiceCreditState =
    notes.length === 0 ? 'none' : invoice.credit_state === 'total' ? 'total' : 'partial'
  return { notes, state }
}

/** A total credit note leaves nothing to pay: the invoice is no longer « to pay ». */
export function nothingLeftToPay(credits: InvoiceCredits): boolean {
  return credits.state === 'total'
}
