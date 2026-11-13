import { AlertTriangle, CreditCard, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { billingApi } from '@/api'
import {
  closeInvoiceForTheSession,
  invoiceAmount,
  invoiceClosedForTheSession,
  invoiceDueOf,
  invoicePeriod,
} from '@/components/billing/invoiceDue'
import { day } from '@/lib/format'
import { subscriptionBannerOf } from '@/lib/subscriptionBanner'
import { useAuthStore } from '@/store/authStore'
import type { BillingSubscription } from '@/types'

/** Closed for this tab only: the reminder comes back at the next visit (the owner, 8 Nov 2026). */
const DISMISSED = 'lecomptoirinvest-billing-start-banner-closed'

function dismissedForTheSession(): boolean {
  try {
    return sessionStorage.getItem(DISMISSED) === '1'
  } catch {
    return false
  }
}

/**
 * What the SUBSCRIBER is told about their own subscription, at the top of every screen
 * (decisions of the owner, 8 Nov 2026), and only them: the licence holder pays, the team
 * does not.
 *
 *  - suspended for an unpaid invoice: red, where to settle, never closable;
 *  - the licence has ended: red, where to subscribe again, never closable (9 Nov 2026);
 *  - a debit that failed, in the grace period: amber, until when to settle;
 *  - the plan becomes paid on a coming date and no payment method is on file: blue,
 *    closable for the session.
 *
 * Silent on failure: an informational banner must not add an error to the screen.
 */
export function SubscriptionBanner() {
  const { t, i18n } = useTranslation()
  const role = useAuthStore((s) => s.role)
  const [info, setInfo] = useState<BillingSubscription | null>(null)
  const [isDemo, setIsDemo] = useState<boolean | null>(null)
  const [closed, setClosed] = useState(dismissedForTheSession)
  const [, setInvoiceClosed] = useState(0)

  useEffect(() => {
    if (role !== 'manager') return
    billingApi
      .mine()
      .then((r) => setInfo(r.data))
      .catch(() => setInfo(null))
    billingApi
      .status()
      .then((r) => setIsDemo(!!r.data.is_demo))
      .catch(() => setIsDemo(null))
  }, [role])

  const kind = subscriptionBannerOf(info, isDemo)
  if (!info || !kind) return null
  if (kind === 'billing-starts' && closed) return null
  const invoice = invoiceDueOf(info.invoice_due)
  if (kind === 'invoice-due' && invoice && invoiceClosedForTheSession(invoice.number)) return null

  const tone =
    kind === 'suspended' || kind === 'ended'
      ? 'bg-red-50 text-red-800'
      : kind === 'payment-failed' || kind === 'invoice-overdue'
        ? 'bg-amber-50 text-amber-900'
        : 'bg-blue-50 text-blue-900'
  const Icon = kind === 'billing-starts' || kind === 'invoice-due' ? CreditCard : AlertTriangle
  // The month in full and the amount in the invoice's currency, in the reader's language.
  const locale = i18n.resolvedLanguage || i18n.language || 'fr'
  const owed = invoice && {
    period: invoicePeriod(invoice, locale),
    amount: invoiceAmount(invoice, locale),
    date: day(invoice.due_on),
  }
  const text =
    kind === 'ended'
      ? info.exports_open && info.export_until
        ? t('subscriptionBanner.endedExports', { date: day(info.export_until) })
        : t('subscriptionBanner.ended')
      : kind === 'suspended'
        ? info.suspension_on
          ? t('subscriptionBanner.suspendedSince', { date: day(info.suspension_on) })
          : t('subscriptionBanner.suspended')
        : kind === 'payment-failed'
          ? info.suspension_on
            ? t('subscriptionBanner.paymentFailed', {
                failed: day(info.payment_failed_on),
                deadline: day(info.suspension_on),
              })
            : t('subscriptionBanner.paymentFailedNoDeadline', { failed: day(info.payment_failed_on) })
          : kind === 'invoice-overdue' && owed
            ? t('subscriptionBanner.invoiceOverdue', owed)
            : kind === 'invoice-due' && owed
              ? t('subscriptionBanner.invoiceDue', owed)
              : t('subscriptionBanner.billingStarts', { date: day(info.billing_starts_on) })

  return (
    <div role="status" className={`flex items-start gap-2 px-4 sm:px-6 lg:px-8 py-2.5 text-sm ${tone}`}>
      <Icon size={16} className="mt-0.5 shrink-0" />
      <p className="flex-1 min-w-0">
        {text}{' '}
        <Link to="/billing" className="font-semibold underline underline-offset-2">
          {kind === 'ended' ? t('subscriptionBanner.subscribeAgain') : t('subscriptionBanner.open')}
        </Link>
      </p>
      {(kind === 'billing-starts' || kind === 'invoice-due') && (
        <button
          type="button"
          aria-label={t('subscriptionBanner.close')}
          title={t('subscriptionBanner.close')}
          onClick={() => {
            if (kind === 'invoice-due' && invoice) {
              closeInvoiceForTheSession(invoice.number)
              setInvoiceClosed((n) => n + 1)
              return
            }
            try {
              sessionStorage.setItem(DISMISSED, '1')
            } catch {
              // Storage refused: closed until the next reload, which is still a close.
            }
            setClosed(true)
          }}
          className="shrink-0 rounded p-0.5 hover:bg-blue-100"
        >
          <X size={16} />
        </button>
      )}
    </div>
  )
}
