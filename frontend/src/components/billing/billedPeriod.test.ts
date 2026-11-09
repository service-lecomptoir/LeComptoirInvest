import { describe, expect, it } from 'vitest'
import { billingStartsOn, periodBilled, planPayment } from './billedPeriod'
import SOURCE from './billedPeriod.ts?raw'

/**
 * The owner, 9 Nov 2026: « Mon abonnement » read « À régler » and « Payer mon abonnement »
 * on 9 November for an account whose first invoice is on 1 January 2027. Alice says whether
 * the month is billed (`current_period_billed`); `billedPeriod.ts` is the same file in every
 * product that reads it, and this guard is the same in every product too.
 */

describe('the current month, as Alice tells it', () => {
  it('is not billed before the start: nothing owed, a means of payment to add', () => {
    const before = { current_period_billed: false, billing_starts_on: '2027-01-01' }
    expect(periodBilled(before)).toBe(false)
    expect(planPayment(before)).toBe('add-method')
    expect(billingStartsOn(before)).toBe('2027-01-01')
  })

  it('is billed once the start is reached, or when no start is set', () => {
    expect(periodBilled({ current_period_billed: true, billing_starts_on: '2026-11-01' })).toBe(true)
    expect(periodBilled({ current_period_billed: true, billing_starts_on: null })).toBe(true)
    expect(planPayment({ current_period_billed: true })).toBe('pay')
    expect(billingStartsOn({ current_period_billed: true, billing_starts_on: null })).toBeNull()
  })

  it('reads an older Alice, which leaves the field out, as billed', () => {
    expect(periodBilled({})).toBe(true)
    expect(periodBilled(null)).toBe(true)
    expect(periodBilled(undefined)).toBe(true)
    expect(planPayment({})).toBe('pay')
    expect(billingStartsOn({})).toBeNull()
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
    expect(fingerprint(SOURCE)).toBe('3349d687')
  })
})
