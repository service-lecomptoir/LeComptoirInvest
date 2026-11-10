/**
 * 🔴 THE MONTH IN COURSE: IS IT BILLED, IS IT OWED, AND WHAT « MON ABONNEMENT » OFFERS FOR IT.
 *
 * ONE NEED, ONE CODE (the owner, 10 Nov 2026). The rule lived in two files (periodBilling.ts
 * in PDF, Syndic and BTP; billedPeriod.ts in Compta, Séjour, Invest and Market) and in the
 * pages beside them (`owesCurrent` of Immo, Compta and Invest, RH's `owesCurrentPeriod`).
 * It is this file now, the same in the nine products, under the fingerprint of
 * billedPeriod.test.ts: change one, change them all, and the fingerprint. Le Comptoir Immo's
 * « Mon abonnement » is the model: where the copies disagreed, its rule was kept.
 *
 * 🔴 BEFORE THE BILLING START, NOTHING IS OWED FOR THE MONTH (the owner, 9 Nov 2026: an
 * account billed from 1 January 2027 read « À régler », « Payer mon abonnement » and the bank
 * details in November). Alice says it (`GET /internal/billing/status`: `current_period_billed`
 * and `billing_starts_on`, her docs/BILLING_CONTRACT.md « Before the billing start, nothing is
 * owed »). TOLD, NEVER INFERRED: the absence of an invoice is not a debt, and an older Alice
 * that leaves the field out bills, as before. Before the start the plan is « Actif » and its
 * Checkout adds a means of payment (Alice opens it as a trial until the start).
 *
 * 🔴 WHAT IS OFFERED IS WHAT IS OWED (the owner's recipe, 9 Nov 2026): the month is owed only
 * when it is billed, not paid already (a transfer validated, a card), not a demonstration
 * account, not held by a running subscription, not free, and the licence not ended. A
 * subscriber is never offered the plan's Checkout (a SECOND Stripe subscription, which Alice
 * refuses since, 409 `already_subscribed`): his means of payment changes in the portal. An
 * ended licence owes no month: what it owes is on its issued invoices, and it subscribes
 * again. An issued invoice left unpaid stays owed, start or not.
 *
 * What the page owns stays in the page: whether the card or the transfer is open, a transfer
 * declared, the terms still to tick, and the words said for each answer.
 */

/** The part of Alice's `billing/status` this file reads, as she sends it. */
export interface PeriodBilling {
  has_subscription?: unknown
  /** False while the current month is before the product's billing start. */
  current_period_billed?: unknown
  billing_starts_on?: unknown
  /** The current month is paid already (a validated transfer, a card): nothing is owed. */
  current_period_paid?: unknown
  /** A demonstration account is never billed, so its month is never paid either. */
  is_demo?: unknown
}

/** The plan held, as the page reads it beside Alice's status. */
export interface HeldPlan {
  status: PeriodBilling | null | undefined
  /** The licence ended (its termination ran out): it owes no month, it subscribes again. */
  ended: boolean
  /** The plan's monthly price; null when no plan is held or the page cannot tell its price:
   *  nothing is owed for it. */
  price: number | null | undefined
}

/**
 * Whether Alice bills the current month: false only when she says it is before the start.
 * An Alice older than 9 Nov 2026 omits the key, and an unknown status says nothing: both
 * read as billed, the screen as it was.
 */
export function periodBilled(status: PeriodBilling | null | undefined): boolean {
  return status?.current_period_billed !== false
}

/** The product's billing start (`YYYY-MM-DD`), or null when Alice names none. */
export function billingStartsOn(status: PeriodBilling | null | undefined): string | null {
  const day = status?.billing_starts_on
  return typeof day === 'string' && day ? day : null
}

/** What the button that opens the plan's Checkout does: pay, or before the start add a
 *  means of payment (nothing is charged until then). */
export type PlanPayment = 'pay' | 'add-method'

export function planPayment(status: PeriodBilling | null | undefined): PlanPayment {
  return periodBilled(status) ? 'pay' : 'add-method'
}

/** A running Stripe subscription holds the plan. A closed licence holds none (Alice af6cc43
 *  says so), whatever an older answer still says. */
export function heldBySubscription(plan: HeldPlan): boolean {
  return !plan.ended && !!plan.status?.has_subscription
}

/** A plan with a price, held by no subscription, not a demonstration, the licence open. */
function pricedWithout(plan: HeldPlan): boolean {
  return !plan.ended && !plan.status?.is_demo && !heldBySubscription(plan) && (plan.price ?? 0) > 0
}

/**
 * Whether the current month is still to pay, Immo's `owesCurrent`: billed, not paid, not a
 * demo, not held by a running subscription, not free, and the licence not ended.
 */
export function owesCurrentPeriod(plan: HeldPlan): boolean {
  return pricedWithout(plan) && periodBilled(plan.status) && !plan.status?.current_period_paid
}

/** Whether the plan starts being billed later: « Actif », a means of payment to add. */
export function startsLater(plan: HeldPlan): boolean {
  return pricedWithout(plan) && !periodBilled(plan.status)
}

/**
 * What the plan's Checkout is offered for, or null when it is not: an ended licence
 * subscribes again, a plan billed later adds a means of payment, the month owed is paid.
 * 🔴 NEVER FOR A SUBSCRIBER: his means of payment changes in the portal.
 */
export type PlanCheckout = 'subscribe-again' | 'add-method' | 'pay'

export function planCheckoutOf(plan: HeldPlan): PlanCheckout | null {
  if (plan.ended) return 'subscribe-again'
  if (startsLater(plan)) return 'add-method'
  return owesCurrentPeriod(plan) ? 'pay' : null
}

/**
 * Whether the bank details and « J'ai fait le virement » are offered: when the month is
 * owed, or when an invoice already issued is still to pay (never by a demo).
 */
export function transferOffered(plan: HeldPlan, owesAnInvoice: boolean): boolean {
  return owesCurrentPeriod(plan) || (owesAnInvoice && !plan.status?.is_demo)
}

/** The day nothing is owed before, when the month is not billed yet: null otherwise. */
export function nothingOwedBefore(status: PeriodBilling | null | undefined): string | null {
  if (periodBilled(status) || status?.has_subscription || status?.is_demo) return null
  return billingStartsOn(status)
}

/**
 * The badge beside the plan, in Immo's order: ended, suspended, a payment that failed (🔴
 * NEVER A GREEN « ACTIF » WHILE A PAYMENT HAS FAILED, 8 Nov 2026), a running subscription,
 * the month paid (« À jour », never « Paiement à mettre en place »), a demonstration, before
 * the start (« Actif »: nothing is owed yet), the month owed, a free plan; null when none
 * applies. The page says each one in its own words.
 */
export type PlanBadge =
  | 'ended'
  | 'suspended'
  | 'payment-failed'
  | 'active'
  | 'up-to-date'
  | 'demo'
  | 'to-pay'
  | 'free'

export function planBadgeOf(plan: HeldPlan, licence: { blocked: boolean; paymentFailed: boolean }): PlanBadge | null {
  if (plan.ended) return 'ended'
  if (licence.blocked) return 'suspended'
  if (licence.paymentFailed) return 'payment-failed'
  if (heldBySubscription(plan)) return 'active'
  if (plan.status?.current_period_paid) return 'up-to-date'
  if (plan.status?.is_demo) return 'demo'
  if (!periodBilled(plan.status)) return 'active'
  if (owesCurrentPeriod(plan)) return 'to-pay'
  if (plan.price === 0) return 'free'
  return null
}
