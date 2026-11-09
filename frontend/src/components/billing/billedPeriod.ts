/**
 * Is the current month billed at all? (the owner, 9 Nov 2026: « Mon abonnement » of Immo
 * read « À régler », « Prochaine échéance le 1 décembre 2026 », « Payer mon abonnement »
 * and the transfer details for an account whose first invoice is on 1 January 2027.)
 *
 * Alice says it in `billing/status` (`current_period_billed`, `billing_starts_on`;
 * LeComptoirAlice, docs/BILLING_CONTRACT.md « Before the billing start, nothing is owed »):
 * before the product's billing start no invoice exists for the month, and that absence is
 * not a debt. 🔴 TOLD, NEVER INFERRED: the screen reads her answer, never the absence of an
 * invoice. An older Alice leaves the field out: the month is billed, as before.
 *
 * Before the start, the plan's own payment button adds a means of payment: Alice's Checkout
 * sets a trial until the start, nothing is charged before it. An invoice already issued and
 * left unpaid is still owed, start or not.
 *
 * ⚠️ THE SAME FILE IN EVERY PRODUCT WHOSE « MON ABONNEMENT » READS IT (Séjour, Invest,
 * Market, Compta since 9 Nov 2026), beside invoiceCredits.ts, under the fingerprint of
 * billedPeriod.test.ts: change one, change them all, and the fingerprint.
 */

/** The part of Alice's `billing/status` this file reads. */
export interface PeriodBilling {
  current_period_billed?: unknown
  billing_starts_on?: unknown
}

/** Whether the current month is billed: false only when Alice says it is before the start. */
export function periodBilled(billing: PeriodBilling | null | undefined): boolean {
  return billing?.current_period_billed !== false
}

/** The product's billing start (`YYYY-MM-DD`), or null when Alice names none. */
export function billingStartsOn(billing: PeriodBilling | null | undefined): string | null {
  const day = billing?.billing_starts_on
  return typeof day === 'string' && day ? day : null
}

/** What the button that opens the plan's Checkout does: pay, or before the start add a
 *  means of payment (nothing is charged until then). */
export type PlanPayment = 'pay' | 'add-method'

export function planPayment(billing: PeriodBilling | null | undefined): PlanPayment {
  return periodBilled(billing) ? 'pay' : 'add-method'
}
