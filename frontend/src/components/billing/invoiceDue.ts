/**
 * The invoice still to pay, as Alice names it (the owner, 9 Nov 2026: after the billing
 * start, a subscriber paying by transfer, or with no means of payment, had nothing on
 * screen between the invoice e-mail and the suspension).
 *
 * Alice serves it in `GET /internal/license/{id}` (`invoice_due`; LeComptoirAlice,
 * docs/BILLING_CONTRACT.md): the oldest invoice still owed (billed period, credit notes
 * deducted), with no transfer declared and no Stripe debit on its way; null when nothing is
 * to pay, and for a demonstration account. The product relays it as she sends it. 🔴 TOLD,
 * NEVER INFERRED: the banner reads her answer, never a list of invoices.
 *
 *  - its day still ahead: blue, « à régler avant le … », closable for the session (for THAT
 *    invoice: a new one is told again);
 *  - its day passed (`overdue`): amber, « n'est pas réglée : elle était due le … », never
 *    closable.
 *
 * A suspension, an ended subscription and a refused debit go first; « devient payant »,
 * before the start only, never beside it.
 *
 * ⚠️ THE SAME FILE IN EVERY PRODUCT WHOSE BANNER READS IT (Séjour, Invest, Market, Compta,
 * Syndic, BTP, PDF since 9 Nov 2026), under the fingerprint of invoiceDue.test.ts: change
 * one, change them all, and the fingerprint.
 */

/** Alice's `invoice_due`, as the product relays it. */
export interface InvoiceDue {
  number: string
  period_year: number
  period_month: number
  /** What is left to pay, tax included, credit notes deducted, in `currency`. */
  left_ttc: number
  currency: string
  /** The last day to pay it (`YYYY-MM-DD`). */
  due_on: string
  overdue: boolean
}

/** The invoice when the answer is one; null otherwise (nothing to pay, an older Alice, a
 *  malformed answer: the banner never draws half a sentence). */
export function invoiceDueOf(value: unknown): InvoiceDue | null {
  if (!value || typeof value !== 'object') return null
  const v = value as Record<string, unknown>
  const { number, period_year: year, period_month: month, left_ttc: left, currency, due_on: due } = v
  if (typeof number !== 'string' || !number || typeof currency !== 'string' || !currency) return null
  if (typeof year !== 'number' || typeof month !== 'number' || month < 1 || month > 12) return null
  if (typeof left !== 'number' || !Number.isFinite(left)) return null
  if (typeof due !== 'string' || !/^\d{4}-\d{2}-\d{2}/.test(due)) return null
  if (typeof v.overdue !== 'boolean') return null
  return {
    number,
    period_year: year,
    period_month: month,
    left_ttc: left,
    currency: currency.toUpperCase(),
    due_on: due.slice(0, 10),
    overdue: v.overdue,
  }
}

/** Which invoice reminder, if any. */
export type InvoiceDueKind = 'invoice-due' | 'invoice-overdue'

export function invoiceDueKind(value: unknown): InvoiceDueKind | null {
  const invoice = invoiceDueOf(value)
  if (!invoice) return null
  return invoice.overdue ? 'invoice-overdue' : 'invoice-due'
}

/** The month billed, in full, in the reader's language: « janvier 2027 » (no capital in
 *  French), « January 2027 », « enero de 2027 », « janeiro de 2027 ». */
export function invoicePeriod(invoice: InvoiceDue, locale: string): string {
  // The first of the month on the reader's own calendar: the same month wherever he is.
  const first = new Date(invoice.period_year, invoice.period_month - 1, 1)
  return new Intl.DateTimeFormat(locale, { month: 'long', year: 'numeric' }).format(first)
}

/** What is left to pay, in the INVOICE's currency, with its two decimals, in the reader's
 *  format: « 120,00 € », « €120.00 ». */
export function invoiceAmount(invoice: InvoiceDue, locale: string): string {
  try {
    return new Intl.NumberFormat(locale, {
      style: 'currency',
      currency: invoice.currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(invoice.left_ttc)
  } catch {
    // A currency code the browser does not know: the number and the code, never nothing.
    return `${invoice.left_ttc.toFixed(2)} ${invoice.currency}`
  }
}

/** The invoice whose (blue) reminder was closed in this tab. */
const CLOSED = 'lecomptoir-invoice-due-banner-closed'

/** Whether the reminder of THIS invoice was closed in this tab. */
export function invoiceClosedForTheSession(number: string): boolean {
  try {
    return sessionStorage.getItem(CLOSED) === number
  } catch {
    return false
  }
}

export function closeInvoiceForTheSession(number: string): void {
  try {
    sessionStorage.setItem(CLOSED, number)
  } catch {
    // Storage refused: closed until the next reload, which is still a close.
  }
}
