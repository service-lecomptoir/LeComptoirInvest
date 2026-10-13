import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { CreditCard, Landmark, ExternalLink, FileText } from 'lucide-react'
import { billingApi } from '@/api'
import { apiClient } from '@/api/client'
import { termsApi } from '@/api/terms'
import { Button, Badge } from '@/components/ui'
import {
  Card, EmptyState, Loading, Notice, PageHeader, Pill, TableWrap, Td, Th,
} from '@/components/common/Primitives'
import { AcceptedTerms } from '@/components/terms/AcceptedTerms'
import { TermsCheckbox } from '@/components/terms/TermsBoxes'
import { confirmDialog } from '@/store/confirm'
import { toast } from '@/store/toast'
import { money, day, numericDay } from '@/lib/format'
import { termsBlock, useTermsOverview, type TermsBox } from '@/lib/terms'
import type {
  BillingInvoice, BillingStatus, BillingSubscription, PaymentMethods,
} from '@/types'
import { PlanChangeOffer } from '@/components/billing/PlanChangeOffer'

/**
 * What the manager pays to use this product, and by what means.
 *
 * 🔴 THIS SCREEN DOES NOT SPEAK OF THE SUBSCRIPTIONS TO THE FUNDS. The word
 * « souscription » belongs to the business here, and the neighbouring screen already
 * carries it. Confusing the two in a product whose matter is other people's money would be
 * the worst of savings on vocabulary.
 *
 * 🔴 NO PRICE IS WRITTEN HERE. The offers, the amounts and the state of the subscription
 * come from the console: this screen displays them and triggers actions, it decides none of
 * them. A hard-coded value would become a second truth that nobody would think of updating
 * on the day of a tariff change.
 *
 * ⚠️ « JE NE SAIS PAS » IS NOT « C'EST GRATUIT ». When the console does not answer, or when
 * none drives the instance, the screen says so plainly. Showing an empty subscription at
 * 0 € would let one believe in a right nobody has granted.
 *
 * 🔴 THE TERMS OF SALE LIVE HERE, FOR THE SUBSCRIBER ONLY (the manager, 2 Oct 2026): the
 * version accepted, read-only, and a required box, unticked, before a plan is chosen.
 * Choosing a plan is subscribing: the version ticked travels with it, and the server has
 * Alice record it before anything is paid. A colleague of the firm sees neither: they do
 * not hold the licence.
 */
export default function Billing() {
  const { t, i18n } = useTranslation()
  const [subscription, setSubscription] = useState<BillingSubscription | null>(null)
  const [methods, setMethods] = useState<PaymentMethods | null>(null)
  const [status, setStatus] = useState<BillingStatus | null>(null)
  const [invoices, setInvoices] = useState<BillingInvoice[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<string | null>(null)
  const [refusal, setRefusal] = useState<string | null>(null)

  // The terms of sale: what the subscriber accepted, and the text a plan change asks.
  // Read again after a 409 (a version published while the page was open), unticked.
  const language = i18n.resolvedLanguage || i18n.language || 'fr'
  const [termsRead, setTermsRead] = useState(0)
  const terms = useTermsOverview(termsRead)
  const subscriber = terms?.status?.subscriber ?? false
  const owedVersion = terms?.status?.cgv?.version ?? null
  const [saleBox, setSaleBox] = useState<TermsBox>({ state: 'loading' })
  const [saleTicked, setSaleTicked] = useState(false)
  useEffect(() => {
    if (!terms) return
    // 🔴 « LOADING » IS NOT « NO TERMS »: the status said nothing (the console is silent),
    // so the box cannot be drawn and no plan can be chosen (fail closed, as at sign-up).
    if (!terms.status || terms.status.unavailable) {
      setSaleBox({ state: 'unavailable' })
      return
    }
    if (!subscriber) {
      setSaleBox({ state: 'none' })
      return
    }
    let live = true
    setSaleBox({ state: 'loading' })
    termsApi
      .text({ kind: 'cgv', language, version: owedVersion })
      .then(({ data }): TermsBox => ({ state: 'ready', text: data }))
      .catch((error): TermsBox =>
        error?.response?.status === 404 ? { state: 'none' } : { state: 'unavailable' },
      )
      .then((box) => {
        if (live) setSaleBox(box)
      })
    return () => {
      live = false
    }
  }, [terms, subscriber, owedVersion, language])
  // Why no plan may be chosen yet, or null: nothing before the status is known, then the
  // subscriber's box. Only the subscriber is asked: the server skips the terms of sale for
  // any other account.
  const saleHold = !terms
    ? 'loading'
    : subscriber
      ? termsBlock({ cgu: { state: 'none' }, cgv: saleBox }, true, { cgu: false, cgv: saleTicked })
      : null
  const sale = saleBox.state === 'ready' && saleTicked
    ? { cgv: saleBox.text.version, language }
    : undefined

  // 🔴 THIS IS WHERE STRIPE SENDS THE PAYER BACK, and the screen must recognise it.
  // Without that, a manager who has just paid comes back to a page identical to the one
  // they left: nothing tells them that their payment went through, and the first reflex
  // is to pay again. The parameter is removed from the address as soon as it is read, so
  // that a refresh does not replay the message.
  const [params, setParams] = useSearchParams()
  const [outcome, setOutcome] = useState<'succes' | 'annule' | null>(null)
  useEffect(() => {
    const paid = params.get('paiement')
    if (paid !== 'succes' && paid !== 'annule') return
    setOutcome(paid)
    params.delete('paiement')
    setParams(params, { replace: true })
  }, [params, setParams])

  const load = () => {
    setLoading(true)
    // Independent calls: an unreadable invoice must not carry away the current offer,
    // and a partially available console is worth more than a blank screen.
    Promise.allSettled([
      billingApi.mine(),
      billingApi.paymentMethods(),
      billingApi.status(),
      billingApi.invoices(),
    ]).then(([s, m, st, i]) => {
      if (s.status === 'fulfilled') setSubscription(s.value.data)
      if (m.status === 'fulfilled') setMethods(m.value.data)
      if (st.status === 'fulfilled') setStatus(st.value.data)
      if (i.status === 'fulfilled') setInvoices(i.value.data)
      setLoading(false)
    })
  }
  useEffect(load, [])

  const refusalOf = (error: unknown): string => {
    const answer = (error as { response?: { status?: number; data?: { detail?: unknown } } })?.response
    if (answer?.status === 409) {
      // The terms of sale changed while the page was open: the new text is read again,
      // unticked, and Alice's sentence says why.
      setSaleTicked(false)
      setTermsRead((n) => n + 1)
    }
    const detail = answer?.data?.detail
    return typeof detail === 'string' ? detail : t('billing.unavailable')
  }

  /** Opens the payment page in the same tab: one leaves the product for the time of paying. */
  const goToPayment = async (planId?: string) => {
    setBusy('checkout')
    setRefusal(null)
    try {
      // A plan named here is subscribed to: the terms of sale ticked travel with it.
      const { data } = await billingApi.checkout(planId, planId ? sale : undefined)
      if (data?.url) window.location.href = data.url
      else setRefusal(t('billing.noPaymentPage'))
    } catch (error) {
      setRefusal(refusalOf(error))
    } finally {
      setBusy(null)
    }
  }

  const openPortal = async () => {
    setBusy('portal')
    setRefusal(null)
    try {
      const { data } = await billingApi.portal()
      if (data?.url) window.location.href = data.url
      else setRefusal(t('billing.noPortal'))
    } catch (error) {
      setRefusal(refusalOf(error))
    } finally {
      setBusy(null)
    }
  }

  const declareTransfer = async () => {
    const confirmed = await confirmDialog({
      title: t('billing.declareTitle'),
      message: t('billing.declareMessage'),
      confirmLabel: t('billing.declareConfirm'),
    })
    if (!confirmed) return
    setBusy('transfer')
    setRefusal(null)
    try {
      await billingApi.declareTransfer()
      toast.success(t('billing.declared'))
      load()
    } catch (error) {
      setRefusal(refusalOf(error))
    } finally {
      setBusy(null)
    }
  }


  /** The PDF goes through the authenticated client: a bare address would return a 401. */
  const openInvoice = async (invoice: BillingInvoice) => {
    try {
      const response = await apiClient.get(billingApi.invoicePdfUrl(invoice.id), {
        responseType: 'blob',
        skipErrorToast: true,
      })
      const url = URL.createObjectURL(response.data as Blob)
      window.open(url, '_blank', 'noopener')
      // Released on the next turn: revoking right away would cut off the opening.
      setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } catch {
      toast.error(t('billing.invoiceUnavailable'))
    }
  }

  if (loading) return <Loading label={t('common.loading')} />

  const currency = methods?.currency || 'eur'
  const current = subscription
  const noConsole = current && !current.managed

  return (
    <>
      <PageHeader title={t('billing.title')} subtitle={t('billing.subtitle')} />

      {outcome && (
        <div className="mb-5">
          {outcome === 'succes' ? (
            <Notice tone="info" title={t('billing.paymentDone')}>{t('billing.paymentDoneHint')}</Notice>
          ) : (
            <Notice tone="warn" title={t('billing.paymentCancelled')}>{t('billing.paymentCancelledHint')}</Notice>
          )}
        </div>
      )}

      {refusal && (
        <div className="mb-5">
          <Notice tone="bad" title={t('billing.actionRefused')}>{refusal}</Notice>
        </div>
      )}

      {noConsole ? (
        <Notice tone="info" title={t('billing.notManaged')}>{t('billing.notManagedHint')}</Notice>
      ) : (
        <div className="space-y-5">
          {current?.is_blocked && (
            <Notice tone="bad" title={t('billing.blocked')}>{t('billing.blockedHint')}</Notice>
          )}

          {/* ── The plan: ONE card in every product (the owner, 12 Oct 2026) ─────── */}
          {/* 🔴 The plan, its quantity, its next payment, then the plans by price or the
              single request, drawn from Alice's offer by PlanChangeOffer, the same file in
              every product; the cap, the renewal and the end are its lines now. */}
          <PlanChangeOffer
            saleTerms={sale}
            blocked={saleHold !== null}
            limitLabel={(limit) => (limit != null ? t('billing.investorLimit', { count: limit }) : t('billing.unlimitedInvestors'))}
            onChanged={load}
            usageLabel={(count, limit) =>
              limit != null ? t('billing.usage', { count, limit }) : t('billing.usageUnlimited', { count })
            }
            badges={
              <>
              {status?.has_subscription ? (
                <Badge variant="green">{t('billing.active')}</Badge>
              ) : (
                <Badge variant="gray">{t('billing.notSubscribed')}</Badge>
              )}
              </>
            }
            plansNote={
              <>
            {saleHold === 'unavailable' && (
              <div className="mt-3">
                <Notice tone="warn" title={t('terms.textUnavailable')}>{t('terms.billing.unavailable')}</Notice>
              </div>
            )}
            {saleBox.state === 'ready' && subscriber && (
              <div className="mt-3">
                <TermsCheckbox
                  text={saleBox.text}
                  checked={saleTicked}
                  onChange={setSaleTicked}
                  label={t('terms.signup.acceptCgv')}
                  hint={t('terms.billing.hint', {
                    version: saleBox.text.version,
                    date: numericDay(saleBox.text.effective_from),
                  })}
                />
                {/* Never a silent grey button: what it waits for is said here. */}
                {saleHold === 'unticked' && (
                  <p className="mt-1 ml-6 text-xs text-amber-800">{t('terms.billing.unticked')}</p>
                )}
              </div>
            )}
              </>
            }
          />

          {/* ── The payment methods ───────────────────────────────────────────── */}
          <Card>
            <div className="p-5 sm:p-6">
              <h2 className="text-sm font-semibold text-gray-900">{t('billing.howToPay')}</h2>

              {methods && !methods.card_enabled && !methods.transfer_enabled ? (
                <p className="mt-3 text-sm text-gray-600">{t('billing.noMethod')}</p>
              ) : (
                <div className="mt-4 grid gap-4 sm:grid-cols-2">
                  {methods?.card_enabled && (
                    <div className="rounded-xl border border-gray-200 p-4 flex flex-col">
                      <div className="flex items-center gap-2 text-gray-900">
                        <CreditCard size={16} className="text-brand-teal" />
                        <span className="text-sm font-medium">{t('billing.byCard')}</span>
                      </div>
                      <p className="mt-1.5 text-sm text-gray-600 flex-1">{t('billing.byCardHint')}</p>
                      <div className="mt-4 flex flex-wrap gap-2">
                        <Button
                          onClick={() => goToPayment()}
                          disabled={busy === 'checkout'}
                        >
                          {status?.has_subscription ? t('billing.updateCard') : t('billing.payNow')}
                        </Button>
                        {status?.has_subscription && (
                          <Button variant="secondary" onClick={openPortal} disabled={busy === 'portal'}>
                            <ExternalLink size={14} /> {t('billing.openPortal')}
                          </Button>
                        )}
                      </div>
                    </div>
                  )}

                  {methods?.transfer_enabled && methods.transfer && (
                    <div className="rounded-xl border border-gray-200 p-4 flex flex-col">
                      <div className="flex items-center gap-2 text-gray-900">
                        <Landmark size={16} className="text-brand-teal" />
                        <span className="text-sm font-medium">{t('billing.byTransfer')}</span>
                      </div>
                      <dl className="mt-2 space-y-1 text-sm text-gray-600 flex-1">
                        {methods.transfer.holder && (
                          <div className="flex gap-2">
                            <dt className="text-gray-500 shrink-0">{t('billing.holder')}</dt>
                            <dd className="font-medium text-gray-800">{methods.transfer.holder}</dd>
                          </div>
                        )}
                        {methods.transfer.iban && (
                          <div className="flex gap-2">
                            <dt className="text-gray-500 shrink-0">IBAN</dt>
                            <dd className="font-mono text-[13px] text-gray-800 break-all">
                              {methods.transfer.iban}
                            </dd>
                          </div>
                        )}
                        {methods.transfer.bic && (
                          <div className="flex gap-2">
                            <dt className="text-gray-500 shrink-0">BIC</dt>
                            <dd className="font-mono text-[13px] text-gray-800">{methods.transfer.bic}</dd>
                          </div>
                        )}
                        {methods.transfer.instructions && (
                          <p className="pt-1 text-[13px] text-gray-500">{methods.transfer.instructions}</p>
                        )}
                      </dl>
                      <div className="mt-4">
                        {status?.transfer_pending ? (
                          <Pill tone="warn">{t('billing.transferPending')}</Pill>
                        ) : (
                          <Button variant="secondary" onClick={declareTransfer} disabled={busy === 'transfer'}>
                            {t('billing.declareTransfer')}
                          </Button>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )}
              {/* The hint lives UNDER the row, never in a cell aligned at the bottom, and
                  only when a card payment is on offer: under « aucun moyen de paiement »
                  it spoke of a payment nobody could make. */}
              {methods?.card_enabled && (
                <p className="mt-4 text-xs text-gray-500">{t('billing.methodsHint')}</p>
              )}
            </div>
          </Card>

          {/* ── The terms of sale accepted, for the subscriber ───────────────── */}
          {subscriber && <AcceptedTerms kind="cgv" overview={terms} />}

          {/* ── The invoices ──────────────────────────────────────────────────── */}
          <Card>
            <div className="p-5 sm:p-6 pb-3">
              <h2 className="text-sm font-semibold text-gray-900">{t('billing.invoices')}</h2>
            </div>
            {invoices.length === 0 ? (
              <EmptyState title={t('billing.noInvoice')} icon={<FileText size={28} />}>
                {t('billing.noInvoiceHint')}
              </EmptyState>
            ) : (
              <TableWrap>
                <thead>
                  <tr>
                    <Th>{t('billing.invoiceNumber')}</Th>
                    <Th>{t('billing.period')}</Th>
                    <Th right>{t('common.amount')}</Th>
                    <Th>{t('common.status')}</Th>
                    <Th right>{t('common.actions')}</Th>
                  </tr>
                </thead>
                <tbody>
                  {invoices.map((invoice) => (
                    <tr key={invoice.id}>
                      <Td>{invoice.number || '-'}</Td>
                      <Td>{invoice.period || day(invoice.issued_at)}</Td>
                      <Td right>{money(invoice.amount, currency)}</Td>
                      <Td>
                        {invoice.paid_at ? (
                          <Pill tone="good">{t('billing.paid')}</Pill>
                        ) : (
                          <Pill tone="warn">{t('billing.due')}</Pill>
                        )}
                      </Td>
                      <Td right>
                        <button
                          type="button"
                          onClick={() => openInvoice(invoice)}
                          className="text-sm font-medium text-brand-teal hover:underline"
                        >
                          {t('billing.downloadPdf')}
                        </button>
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </TableWrap>
            )}
          </Card>
        </div>
      )}
    </>
  )
}
