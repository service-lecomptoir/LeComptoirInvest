/**
 * The subscriber's banners and the screens around a suspension (the owner, 8 Nov 2026).
 *
 * The decision is read here on its own; the wiring is read in the sources (`?raw`): the
 * shell mounts the banner, the router keeps a suspended subscriber on « Mon abonnement »,
 * the client carries a closed firm's sentence to the sign-in page, and the subscription
 * screen never shows « Actif » over a failed debit.
 */
import { describe, expect, it } from 'vitest'
import { subscriptionBannerOf } from '@/lib/subscriptionBanner'
import type { BillingSubscription } from '@/types'
import shell from '@/components/layout/Shell.tsx?raw'
import router from '@/router.tsx?raw'
import client from '@/api/client.ts?raw'
import login from '@/pages/Login.tsx?raw'
import billing from '@/pages/Billing.tsx?raw'
import api from '@/api/index.ts?raw'

const TODAY = '2026-11-09'

function info(over: Partial<BillingSubscription> = {}): BillingSubscription {
  return {
    managed: true,
    plan_name: 'Fonds 50',
    monthly_price: 49,
    is_blocked: false,
    features: null,
    access_until: null,
    investor_limit: 50,
    is_holder: true,
    unavailable: false,
    ...over,
  }
}

describe('the banner speaks to the subscriber alone', () => {
  it('says billing starts and asks for a payment method', () => {
    const before = info({ billing_starts_on: '2027-01-01', has_payment_method: false })
    expect(subscriptionBannerOf(before, false, TODAY)).toBe('billing-starts')
  })

  it('says nothing to a colleague, a demonstration, a free plan or a method on file', () => {
    const before = { billing_starts_on: '2027-01-01', has_payment_method: false }
    expect(subscriptionBannerOf(info({ ...before, is_holder: false }), false, TODAY)).toBeNull()
    expect(subscriptionBannerOf(info(before), true, TODAY)).toBeNull()
    expect(subscriptionBannerOf(info({ ...before, monthly_price: 0 }), false, TODAY)).toBeNull()
    expect(subscriptionBannerOf(info({ ...before, has_payment_method: true }), false, TODAY)).toBeNull()
  })

  it('says nothing once billing has started, or for an older Alice that does not say', () => {
    expect(subscriptionBannerOf(info({ billing_starts_on: '2026-01-01', has_payment_method: false }), false, TODAY)).toBeNull()
    expect(subscriptionBannerOf(info(), false, TODAY)).toBeNull()
  })

  it('tells a failed debit and a suspension apart from an ended subscription', () => {
    expect(subscriptionBannerOf(info({ payment_failed_on: '2026-11-02' }), false, TODAY)).toBe('payment-failed')
    expect(subscriptionBannerOf(info({ is_blocked: true, suspended: true }), false, TODAY)).toBe('suspended')
    expect(subscriptionBannerOf(info({ is_blocked: true, suspended: false }), false, TODAY)).toBeNull()
    expect(subscriptionBannerOf(info({ is_blocked: true, suspended: false, ended: true }), false, TODAY)).toBe('ended')
    expect(subscriptionBannerOf(info({ unavailable: true, payment_failed_on: '2026-11-02' }), false, TODAY)).toBeNull()
  })
})

describe('the screens around a suspension', () => {
  it('mounts the banner in the shell', () => {
    expect(shell).toContain('<SubscriptionBanner />')
  })

  it('keeps a suspended subscriber on « Mon abonnement »', () => {
    expect(router).toContain('subscriptionSuspended || subscriptionEnded')
  })

  it('keeps the subscriber of an ended licence on « Mon abonnement », to subscribe again (9 Nov 2026)', () => {
    expect(router).toContain('(subscriptionSuspended || subscriptionEnded) && location.pathname !== SUBSCRIPTION_ROUTE')
    expect(client).toContain('HELD_SUBSCRIBER.includes(code)')
    expect(client).toMatch(/HELD_SUBSCRIBER = \['subscription_suspended', 'licence_ended'\]/)
    expect(billing).toContain("t('billing.ended')")
  })

  it("carries a closed firm's sentence to the sign-in page", () => {
    expect(client).toContain('leaveSessionNotice(errorMessage(error))')
    expect(login).toContain('useState<string | null>(takeSessionNotice)')
  })

  it('never shows « Actif » over a failed debit, and offers a way out on a due invoice', () => {
    expect(billing).toMatch(/paymentFailed \? \(\s*<Badge variant="orange">/)
    expect(billing).toContain("t('billing.invoiceSettle')")
    expect(billing).toContain("t('billing.invoiceByTransfer')")
    expect(billing).toContain("t('billing.infoUnavailable')")
  })

  it('sends the terms ticked when paying the plan in place', () => {
    expect(api).toContain("planId ? { plan_id: planId, ...sale } : { ...sale }")
    expect(billing).toContain('billingApi.checkout(planId, sale)')
  })
})
