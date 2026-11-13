import { invoiceDueKind } from '@/components/billing/invoiceDue'
import type { BillingSubscription } from '@/types'
import { todayIso } from '@/lib/day'
import { day } from '@/lib/format'

/** Which reminder the subscriber is shown, if any (`components/layout/SubscriptionBanner`). */
export type SubscriptionBannerKind = 'suspended' | 'ended' | 'payment-failed' | 'billing-starts'
  /** An issued invoice to pay, its day still ahead (the owner, 9 Nov 2026). */
  | 'invoice-due'
  /** An issued invoice whose day has passed: the suspension may follow. */
  | 'invoice-overdue'

/**
 * The decision, apart from the drawing so it can be read and tested on its own (decisions
 * of the owner, 8 Nov 2026, as on Le Comptoir Immo). Only the licence HOLDER is concerned;
 * an Alice that does not send a field yet shows no banner for it.
 *
 * `isDemo`: a demonstration account is never asked for a payment method; null while the
 * billing status has not said (no reminder until it does).
 */
export function subscriptionBannerOf(
  info: BillingSubscription | null,
  isDemo: boolean | null,
  today: string = todayIso(),
): SubscriptionBannerKind | null {
  if (!info || !info.managed || !info.is_holder || info.unavailable) return null
  // An ended licence keeps its subscriber on « Mon abonnement », to subscribe again (the
  // owner, 9 Nov 2026); an older server that says neither shows nothing.
  if (info.is_blocked) return info.suspended ? 'suspended' : info.ended ? 'ended' : null
  if (info.payment_failed_on) return 'payment-failed'
  // 🔴 THE INVOICE STILL TO PAY (the owner, 9 Nov 2026): after the billing start, a
  // subscriber paying by transfer, or with no means of payment, had nothing on screen
  // between the invoice e-mail and the suspension. Alice names it (none for a
  // demonstration account); it goes before « devient payant », never beside it.
  const invoice = invoiceDueKind(info.invoice_due)
  if (invoice) return invoice
  const startsLater = !!info.billing_starts_on && info.billing_starts_on.slice(0, 10) > today
  if (startsLater && info.has_payment_method === false && (info.monthly_price ?? 0) > 0) {
    return isDemo === false ? 'billing-starts' : null
  }
  return null
}

/**
 * 🔴 A BANNER WRITES ITS DAY JJ/MM/AAAA, IN EVERY LANGUAGE (the owner, 13 Nov 2026): the end
 * of the thirty days to export, the erasure of the data, the new terms. Through the one
 * door to a written day (`lib/format.day`), with the pattern, never a formatter of its own.
 */
export function bannerDay(value: string | null | undefined): string {
  return day(value, 'dd/MM/yyyy')
}

/**
 * The words of the « ended » banner: the thirty days to read and export while they run,
 * and the day the data are erased once Alice and this product agree on one (13 Nov 2026).
 */
export function endedWords(
  info: Pick<BillingSubscription, 'exports_open' | 'export_until' | 'erase_on'>,
  t: (key: string, vars?: Record<string, string>) => string,
): string {
  const head =
    info.exports_open && info.export_until
      ? t('subscriptionBanner.endedExports', { date: bannerDay(info.export_until) })
      : t('subscriptionBanner.ended')
  return info.erase_on
    ? `${head} ${t('subscriptionBanner.erasedOn', { date: bannerDay(info.erase_on) })}`
    : head
}
