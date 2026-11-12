import { describe, expect, it } from 'vitest'
import {
  billingStartsOn, meansSettledBeforeStart, nothingOwedBefore, owesCurrentPeriod, periodBilled, planBadgeOf,
  planCheckoutOf, planPayment, startsLater, heldBySubscription, transferOffered, type HeldPlan, type PeriodBilling,
} from './billedPeriod'
import SOURCE from './billedPeriod.ts?raw'

/**
 * The month in course, as « Mon abonnement » reads it in every product (the owner, 10 Nov
 * 2026: one need, one code). The cases below fixed what each copy said before they became
 * this one file (periodBilling.ts of PDF, Syndic and BTP; billedPeriod.ts and the pages of
 * Compta, Séjour, Invest and Market; Immo's and RH's `owesCurrent`): they all agreed on
 * them. This test is the same in every product too.
 */

const BILLED: PeriodBilling = { has_subscription: false, current_period_billed: true, current_period_paid: false, is_demo: false }
const plan = (status: PeriodBilling | null | undefined, more: Partial<HeldPlan> = {}): HeldPlan =>
  ({ status, ended: false, price: 29, hasPaymentMethod: undefined, ...more })
const OPEN = { blocked: false, paymentFailed: false }

describe('the month billed and not paid', () => {
  const owed = plan(BILLED)

  it('is owed: the plan is paid by its Checkout or by transfer, « to pay »', () => {
    expect(periodBilled(BILLED)).toBe(true)
    expect(owesCurrentPeriod(owed)).toBe(true)
    expect(planCheckoutOf(owed)).toBe('pay')
    expect(planPayment(BILLED)).toBe('pay')
    expect(transferOffered(owed, false)).toBe(true)
    expect(planBadgeOf(owed, OPEN)).toBe('to-pay')
    expect(nothingOwedBefore(BILLED)).toBeNull()
  })

  it('reads an older Alice, which leaves the field out, and an unknown status, as billed', () => {
    expect(periodBilled({})).toBe(true)
    expect(periodBilled(null)).toBe(true)
    expect(periodBilled(undefined)).toBe(true)
    expect(planPayment({})).toBe('pay')
    expect(owesCurrentPeriod(plan({}))).toBe(true)
  })
})

describe('the month paid (a payer by transfer up to date, a card)', () => {
  const paid = plan({ ...BILLED, current_period_paid: true })

  it('is not asked again: « up to date », no Checkout, no transfer', () => {
    expect(owesCurrentPeriod(paid)).toBe(false)
    expect(planCheckoutOf(paid)).toBeNull()
    expect(transferOffered(paid, false)).toBe(false)
    expect(planBadgeOf(paid, OPEN)).toBe('up-to-date')
  })

  it('still offers the transfer for an invoice issued and left unpaid', () => {
    expect(transferOffered(paid, true)).toBe(true)
  })
})

describe('a running subscription', () => {
  const held = plan({ ...BILLED, has_subscription: true })

  it('owes nothing here and is never offered the Checkout (a second subscription)', () => {
    expect(heldBySubscription(held)).toBe(true)
    expect(owesCurrentPeriod(held)).toBe(false)
    expect(planCheckoutOf(held)).toBeNull()
    expect(planCheckoutOf(plan({ ...BILLED, has_subscription: true, current_period_billed: false }))).toBeNull()
    expect(planBadgeOf(held, OPEN)).toBe('active')
  })
})

describe('a demonstration account', () => {
  const demo = plan({ ...BILLED, is_demo: true })

  it('is never billed: nothing owed, no Checkout, no transfer even for an invoice', () => {
    expect(owesCurrentPeriod(demo)).toBe(false)
    expect(planCheckoutOf(demo)).toBeNull()
    expect(transferOffered(demo, true)).toBe(false)
    expect(planBadgeOf(demo, OPEN)).toBe('demo')
    expect(nothingOwedBefore({ ...BILLED, is_demo: true, current_period_billed: false, billing_starts_on: '2027-01-01' })).toBeNull()
  })
})

describe('before the billing start', () => {
  const before: PeriodBilling = { ...BILLED, current_period_billed: false, billing_starts_on: '2027-01-01' }
  const later = plan(before)

  it('owes nothing for the month: « active », a means of payment to add, no transfer', () => {
    expect(periodBilled(before)).toBe(false)
    expect(owesCurrentPeriod(later)).toBe(false)
    expect(startsLater(later)).toBe(true)
    expect(planCheckoutOf(later)).toBe('add-method')
    expect(planPayment(before)).toBe('add-method')
    expect(transferOffered(later, false)).toBe(false)
    expect(planBadgeOf(later, OPEN)).toBe('active')
    expect(billingStartsOn(before)).toBe('2027-01-01')
    expect(nothingOwedBefore(before)).toBe('2027-01-01')
  })

  it('still owes an invoice already issued and left unpaid', () => {
    expect(transferOffered(later, true)).toBe(true)
  })

  it('adds a means of payment only when Alice does not say it is settled (the owner, 12 Nov 2026)', () => {
    // A payer by transfer (« Paie par virement » on Alice's console): nothing to add.
    const byTransfer = plan(before, { hasPaymentMethod: true })
    expect(planCheckoutOf(byTransfer)).toBeNull()
    expect(meansSettledBeforeStart(byTransfer)).toBe(true)
    expect(planBadgeOf(byTransfer, OPEN)).toBe('active')
    expect(transferOffered(byTransfer, false)).toBe(false)
    // No means of payment: the Checkout records one.
    const without = plan(before, { hasPaymentMethod: false })
    expect(planCheckoutOf(without)).toBe('add-method')
    expect(meansSettledBeforeStart(without)).toBe(false)
    // Alice silent (an older one, an outage): as before.
    for (const hasPaymentMethod of [null, undefined]) {
      expect(planCheckoutOf(plan(before, { hasPaymentMethod }))).toBe('add-method')
      expect(meansSettledBeforeStart(plan(before, { hasPaymentMethod }))).toBe(false)
    }
  })

  it('changes nothing else: the month owed, an ended licence, a subscriber', () => {
    expect(planCheckoutOf(plan(BILLED, { hasPaymentMethod: true }))).toBe('pay')
    expect(planCheckoutOf(plan(before, { ended: true, hasPaymentMethod: true }))).toBe('subscribe-again')
    expect(meansSettledBeforeStart(plan({ ...before, has_subscription: true }, { hasPaymentMethod: true }))).toBe(false)
    expect(meansSettledBeforeStart(plan(BILLED, { hasPaymentMethod: true }))).toBe(false)
  })

  it('names no day when Alice names none, or once the start is reached', () => {
    expect(billingStartsOn({ current_period_billed: true, billing_starts_on: null })).toBeNull()
    expect(billingStartsOn({})).toBeNull()
    expect(nothingOwedBefore({ ...BILLED, billing_starts_on: '2026-11-01' })).toBeNull()
  })
})

describe('a licence closed (its termination ran out)', () => {
  const ended = plan(BILLED, { ended: true })

  it('owes no month, subscribes again, and settles its invoices one by one', () => {
    expect(owesCurrentPeriod(ended)).toBe(false)
    expect(startsLater(plan({ ...BILLED, current_period_billed: false }, { ended: true }))).toBe(false)
    expect(planCheckoutOf(ended)).toBe('subscribe-again')
    expect(transferOffered(ended, false)).toBe(false)
    expect(transferOffered(ended, true)).toBe(true)
    expect(planBadgeOf(ended, { blocked: true, paymentFailed: false })).toBe('ended')
  })

  it('holds no subscription, whatever an older answer still says', () => {
    expect(heldBySubscription(plan({ ...BILLED, has_subscription: true }, { ended: true }))).toBe(false)
  })
})

describe('a free plan, or a price the page cannot tell', () => {
  it('owes nothing and offers no Checkout', () => {
    for (const price of [0, null, undefined]) {
      expect(owesCurrentPeriod(plan(BILLED, { price }))).toBe(false)
      expect(planCheckoutOf(plan(BILLED, { price }))).toBeNull()
      expect(transferOffered(plan(BILLED, { price }), false)).toBe(false)
    }
    expect(planBadgeOf(plan(BILLED, { price: 0 }), OPEN)).toBe('free')
    expect(planBadgeOf(plan(BILLED, { price: null }), OPEN)).toBeNull()
  })
})

describe('the badge beside the plan', () => {
  it("follows Immo's order: suspended, then a payment that failed, before anything else", () => {
    expect(planBadgeOf(plan(BILLED), { blocked: true, paymentFailed: true })).toBe('suspended')
    expect(planBadgeOf(plan({ ...BILLED, has_subscription: true }), { blocked: false, paymentFailed: true })).toBe('payment-failed')
    expect(planBadgeOf(plan({ ...BILLED, has_subscription: true, current_period_paid: true }), OPEN)).toBe('active')
    expect(planBadgeOf(plan({ ...BILLED, current_period_paid: true, is_demo: true }), OPEN)).toBe('up-to-date')
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

  it('is the shared billedPeriod.ts: change one, change them all', () => {
    expect(fingerprint(SOURCE)).toBe('7c14c985')
  })
})
