import { Fragment, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { CreditCard, Landmark, ExternalLink, FileText } from 'lucide-react'
import { billingApi } from '@/api'
import { apiClient } from '@/api/client'
import { SUBSCRIBER_KINDS, termsApi, type SubscriberKind } from '@/api/terms'
import { Button, Badge } from '@/components/ui'
import {
  Card, EmptyState, Loading, Notice, PageHeader, Pill, TableWrap, Td, Th,
} from '@/components/common/Primitives'
import { AcceptedTerms } from '@/components/terms/AcceptedTerms'
import { TermsCheckbox } from '@/components/terms/TermsBoxes'
import { confirmDialog } from '@/store/confirm'
import { toast } from '@/store/toast'
import { money, day, numericDay } from '@/lib/format'
import { stillOwed, termsBlock, useTermsOverview, type TermsBox } from '@/lib/terms'
import type {
  BillingInvoice, BillingStatus, BillingSubscription, PaymentMethods,
} from '@/types'
import { PlanChangeOffer } from '@/components/billing/PlanChangeOffer'
import { creditsOf, nothingLeftToPay, type InvoiceCreditNote } from '@/components/billing/invoiceCredits'
import { billingStartsOn, periodBilled, planPayment } from '@/components/billing/billedPeriod'

/**
 * The month an invoice bills, « MM/YYYY », from what Alice sends (`period_month`,
 * `period_year`). Until 6 Nov 2026 this screen read `period` and `issued_at`, which Alice
 * never sent: the column came out empty. Both stay as fallbacks.
 */
function periodOf(invoice: BillingInvoice): string {
  const { period_month: month, period_year: year } = invoice
  if (month && year) return `${String(month).padStart(2, '0')}/${year}`
  return invoice.period || day(invoice.issued_at || invoice.created_at)
}

/**
 * What the invoice asked, tax included (the amount before tax only on the oldest ones), in
 * ITS currency, the one Alice billed it in, never the one of the payment methods (8 Nov 2026,
 * Le Comptoir Immo's fix of 7 Nov). An older Alice that names none billed in euros only.
 */
function invoiceAmountSaid(invoice: BillingInvoice): string {
  const amount = Number(invoice.amount_ttc) > 0 ? invoice.amount_ttc : invoice.amount
  return money(amount, invoice.currency || 'EUR')
}

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
 *
 * 🔴 AND THE DATA PROCESSING AGREEMENT BESIDE THEM (the owner, 13 Oct 2026): a second box on
 * the same rule, its sub-processors listed under its text, its acceptance read-only below.
 * Asked only when the console serves it (absent from an older status: nothing is asked).
 */
const LOADING: TermsBox = { state: 'loading' }
const NONE: TermsBox = { state: 'none' }
const UNAVAILABLE: TermsBox = { state: 'unavailable' }

/** What the subscriber is told while a box waits, document by document. */
const UNTICKED_HINT: Record<SubscriberKind, string> = {
  cgv: 'terms.billing.unticked',
  dpa: 'terms.billing.untickedDpa',
}
const UNAVAILABLE_HINT: Record<SubscriberKind, string> = {
  cgv: 'terms.billing.unavailable',
  dpa: 'terms.billing.unavailableDpa',
}
const ACCEPT_LABEL: Record<SubscriberKind, string> = {
  cgv: 'terms.signup.acceptCgv',
  dpa: 'terms.signup.acceptDpa',
}

export default function Billing() {
  const { t, i18n } = useTranslation()
  const [subscription, setSubscription] = useState<BillingSubscription | null>(null)
  const [methods, setMethods] = useState<PaymentMethods | null>(null)
  const [status, setStatus] = useState<BillingStatus | null>(null)
  const [invoices, setInvoices] = useState<BillingInvoice[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<string | null>(null)
  const [refusal, setRefusal] = useState<string | null>(null)

  // The terms of sale and the agreement: what the subscriber accepted, and the texts a plan
  // change asks. Read again after a 409 (a version published while the page was open),
  // unticked.
  const language = i18n.resolvedLanguage || i18n.language || 'fr'
  const [termsRead, setTermsRead] = useState(0)
  const terms = useTermsOverview(termsRead)
  const subscriber = terms?.status?.subscriber ?? false
  // 🔴 ONLY WHAT IS STILL OWED IS ASKED (the owner, 1 Nov 2026, Immo's rule): the version
  // in force already accepted is not asked again, a new one is; nothing owed, no box, and
  // the change goes straight through. The server applies the same rule.
  const saleVersion = stillOwed(terms?.status?.cgv)?.version ?? null
  const dpaVersion = stillOwed(terms?.status?.dpa)?.version ?? null
  const [boxes, setBoxes] = useState<Record<SubscriberKind, TermsBox>>({ cgv: LOADING, dpa: LOADING })
  const [ticked, setTicked] = useState<Record<SubscriberKind, boolean>>({ cgv: false, dpa: false })
  useEffect(() => {
    if (!terms) return
    // 🔴 « LOADING » IS NOT « NO TERMS »: the status said nothing (the console is silent),
    // so the box cannot be drawn and no plan can be chosen (fail closed, as at sign-up).
    // One notice says it: the agreement waits behind the terms of sale.
    if (!terms.status || terms.status.unavailable) {
      setBoxes({ cgv: UNAVAILABLE, dpa: NONE })
      return
    }
    if (!subscriber) {
      setBoxes({ cgv: NONE, dpa: NONE })
      return
    }
    let live = true
    const read = (kind: SubscriberKind, version: string | null) =>
      termsApi
        .text({ kind, language, version })
        .then(({ data }): TermsBox => ({ state: 'ready', text: data }))
        .catch((error): TermsBox => (error?.response?.status === 404 ? NONE : UNAVAILABLE))
        .then((box) => {
          if (live) setBoxes((was) => ({ ...was, [kind]: box }))
        })
    setBoxes({ cgv: saleVersion ? LOADING : NONE, dpa: dpaVersion ? LOADING : NONE })
    if (saleVersion) void read('cgv', saleVersion)
    if (dpaVersion) void read('dpa', dpaVersion)
    return () => {
      live = false
    }
  }, [terms, subscriber, saleVersion, dpaVersion, language])
  // Why no plan may be chosen yet, or null: nothing before the status is known, then the
  // subscriber's boxes. Only the subscriber is asked: the server skips the terms of sale
  // and the agreement for any other account.
  const saleHold = !terms
    ? 'loading'
    : subscriber
      ? termsBlock({ cgu: NONE, ...boxes }, true, { cgu: false, ...ticked })
      : null
  const versionTicked = (kind: SubscriberKind): string | null => {
    const box = boxes[kind]
    return box.state === 'ready' && ticked[kind] ? box.text.version : null
  }
  const sale = versionTicked('cgv') || versionTicked('dpa')
    ? { cgv: versionTicked('cgv'), dpa: versionTicked('dpa'), language }
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
      // The terms of sale or the agreement changed while the page was open: the new text
      // is read again, unticked, and Alice's sentence says why.
      setTicked({ cgv: false, dpa: false })
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
      // A plan named here is subscribed to, and paying the plan in place is a sale too (the
      // owner, 8 Nov 2026): the terms ticked travel with it, and the server checks them.
      const { data } = await billingApi.checkout(planId, sale)
      if (data?.url) window.location.href = data.url
      else setRefusal(t('billing.noPaymentPage'))
    } catch (error) {
      setRefusal(refusalOf(error))
    } finally {
      setBusy(null)
    }
  }

  /** An ended licence settles ONE invoice, never subscribes again by paying it (the owner,
   *  9 Nov 2026): Alice's `pay-invoice`, not the Checkout of the plan nor the portal. */
  const payInvoice = async (invoice: BillingInvoice) => {
    setBusy('checkout')
    setRefusal(null)
    try {
      const { data } = await billingApi.payInvoice(invoice.id)
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

  /** A credit note's PDF, the same way (the owner, 6 Nov 2026: the credit notes shown). */
  const openCreditNote = async (note: InvoiceCreditNote) => {
    try {
      const response = await apiClient.get(billingApi.creditNotePdfUrl(note.id), {
        responseType: 'blob',
        skipErrorToast: true,
      })
      const url = URL.createObjectURL(response.data as Blob)
      window.open(url, '_blank', 'noopener')
      setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } catch {
      toast.error(t('billing.creditNoteUnavailable'))
    }
  }

  if (loading) return <Loading label={t('common.loading')} />

  const current = subscription
  const noConsole = current && !current.managed
  // 🔴 A DEBIT THAT FAILED IS NOT « ACTIF » (the owner, 8 Nov 2026): while it is being
  // settled, the badge says so.
  const paymentFailed = !current?.is_blocked && !!current?.payment_failed_on
  // Paying the plan in place waits on the terms still owed, as a plan change does.
  const payHeld = subscriber && saleHold !== null
  /** An issued invoice still to pay: not paid, and not cancelled by its credit notes. */
  const owes = (invoice: BillingInvoice) => !invoice.paid_at && !nothingLeftToPay(creditsOf(invoice))
  // 🔴 BEFORE THE BILLING START NOTHING IS OWED (the owner, 9 Nov 2026: « À régler », « Payer
  // mon abonnement » and the transfer details on 9 November for a first invoice on 1 January
  // 2027). Alice says whether the month is billed: before the start the plan is « Actif »,
  // the card adds a means of payment (nothing charged), and no transfer is declared for a
  // month nobody owes; an invoice already issued and unpaid is still owed.
  const startsLater =
    !status?.has_subscription && !status?.is_demo && !current?.ended && !paymentFailed && !periodBilled(status)
  const transferShown = periodBilled(status) || invoices.some(owes)
  const nothingChargedBefore = t('billing.nothingChargedBefore', { day: numericDay(billingStartsOn(status)) })

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

      {current?.unavailable ? (
        /* Alice did not answer: an empty plan here would read as « no plan » (8 Nov 2026). */
        <Notice tone="warn" title={t('billing.actionRefused')}>{t('billing.infoUnavailable')}</Notice>
      ) : noConsole ? (
        <Notice tone="info" title={t('billing.notManaged')}>{t('billing.notManagedHint')}</Notice>
      ) : (
        <div className="space-y-5">
          {/* An ended licence keeps « Mon abonnement »: its invoices, what is still due, and
              the plans below to subscribe again (the owner, 9 Nov 2026). */}
          {current?.is_blocked &&
            (current.ended ? (
              <Notice tone="bad" title={t('billing.ended')}>{t('billing.endedHint')}</Notice>
            ) : (
              <Notice tone="bad" title={t('billing.blocked')}>{t('billing.blockedHint')}</Notice>
            ))}

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
              {paymentFailed ? (
                <Badge variant="orange">{t('billing.paymentFailed')}</Badge>
              ) : status?.has_subscription || startsLater ? (
                <Badge variant="green">{t('billing.active')}</Badge>
              ) : (
                <Badge variant="gray">{t('billing.notSubscribed')}</Badge>
              )}
              </>
            }
            plansNote={
              <>
            {SUBSCRIBER_KINDS.map((kind) => {
              const box = boxes[kind]
              if (box.state === 'unavailable') {
                if (saleHold !== 'unavailable') return null
                return (
                  <div key={kind} className="mt-3">
                    <Notice tone="warn" title={t('terms.textUnavailable')}>{t(UNAVAILABLE_HINT[kind])}</Notice>
                  </div>
                )
              }
              if (box.state !== 'ready' || !subscriber) return null
              return (
                <div key={kind} className="mt-3">
                  <TermsCheckbox
                    mustRead
                    text={box.text}
                    checked={ticked[kind]}
                    onChange={(checked) => setTicked((was) => ({ ...was, [kind]: checked }))}
                    label={t(ACCEPT_LABEL[kind])}
                    hint={t('terms.billing.hint', {
                      version: box.text.version,
                      date: numericDay(box.text.effective_from),
                    })}
                  />
                  {/* Never a silent grey button: what it waits for is said here. */}
                  {saleHold === 'unticked' && !ticked[kind] && (
                    <p className="mt-1 ml-6 text-xs text-amber-800">{t(UNTICKED_HINT[kind])}</p>
                  )}
                </div>
              )
            })}
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
                      <p className="mt-1.5 text-sm text-gray-600 flex-1">
                        {startsLater ? nothingChargedBefore : t('billing.byCardHint')}
                      </p>
                      {/* Never a silent grey button: what it waits for is said here. */}
                      {payHeld && <p className="mt-2 text-xs text-amber-800">{t('billing.termsFirst')}</p>}
                      <div className="mt-4 flex flex-wrap gap-2">
                        <Button
                          onClick={() => goToPayment()}
                          disabled={busy === 'checkout' || payHeld}
                        >
                          {status?.has_subscription
                            ? t('billing.updateCard')
                            : planPayment(status) === 'add-method'
                              ? t('billing.addMethod')
                              : t('billing.payNow')}
                        </Button>
                        {status?.has_subscription && (
                          <Button variant="secondary" onClick={openPortal} disabled={busy === 'portal'}>
                            <ExternalLink size={14} /> {t('billing.openPortal')}
                          </Button>
                        )}
                      </div>
                    </div>
                  )}

                  {methods?.transfer_enabled && methods.transfer && transferShown && (
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
              {/* Without the card, the month not billed yet is said here. */}
              {startsLater && !methods?.card_enabled && (
                <p className="mt-4 text-xs text-gray-500">{nothingChargedBefore}</p>
              )}
            </div>
          </Card>

          {/* ── The terms of sale and the agreement accepted, for the subscriber ── */}
          {subscriber && <AcceptedTerms kind="cgv" overview={terms} />}
          {subscriber && <AcceptedTerms kind="dpa" overview={terms} />}

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
                  {invoices.map((invoice) => {
                    // 🔴 THE CREDIT NOTES UNDER THEIR INVOICE (the owner, 6 Nov 2026): a badge
                    // beside the status, then one line per note; a total one leaves nothing due.
                    const credits = creditsOf(invoice)
                    return (
                      <Fragment key={invoice.id}>
                        <tr>
                          <Td>{invoice.number || '-'}</Td>
                          <Td>{periodOf(invoice)}</Td>
                          <Td right>{invoiceAmountSaid(invoice)}</Td>
                          <Td>
                            <span className="inline-flex flex-wrap items-center gap-1.5">
                              {invoice.paid_at ? (
                                <Pill tone="good">{t('billing.paid')}</Pill>
                              ) : (
                                !nothingLeftToPay(credits) && <Pill tone="warn">{t('billing.due')}</Pill>
                              )}
                              {credits.state === 'partial' && <Pill tone="info">{t('billing.creditPartial')}</Pill>}
                              {credits.state === 'total' && <Pill tone="info">{t('billing.creditTotal')}</Pill>}
                            </span>
                          </Td>
                          <Td right>
                            <span className="inline-flex flex-wrap items-center justify-end gap-x-3 gap-y-1">
                              {/* 🔴 « À RÉGLER » WITH NOTHING TO CLICK (the owner, 8 Nov 2026): an
                                  unpaid invoice offers its way out, on its own line. */}
                              {owes(invoice) && !status?.is_demo && (
                                status?.transfer_pending ? (
                                  <span className="text-xs text-amber-800">{t('billing.transferPending')}</span>
                                ) : (
                                  <>
                                    {current?.ended ? (
                                      methods?.card_enabled ? (
                                        <button
                                          type="button"
                                          onClick={() => payInvoice(invoice)}
                                          disabled={busy === 'checkout'}
                                          className="text-sm font-medium text-brand-teal hover:underline disabled:opacity-60"
                                        >
                                          {t('billing.invoicePayByCard')}
                                        </button>
                                      ) : null
                                    ) : status?.has_subscription ? (
                                      <button
                                        type="button"
                                        onClick={openPortal}
                                        disabled={busy === 'portal'}
                                        className="text-sm font-medium text-brand-teal hover:underline disabled:opacity-60"
                                      >
                                        {t('billing.invoiceSettle')}
                                      </button>
                                    ) : methods?.card_enabled ? (
                                      <button
                                        type="button"
                                        onClick={() => goToPayment()}
                                        disabled={busy === 'checkout' || payHeld}
                                        className="text-sm font-medium text-brand-teal hover:underline disabled:opacity-60"
                                      >
                                        {t('billing.invoicePayByCard')}
                                      </button>
                                    ) : null}
                                    {methods?.transfer_enabled && (
                                      <button
                                        type="button"
                                        onClick={declareTransfer}
                                        disabled={busy === 'transfer'}
                                        className="text-sm font-medium text-gray-700 hover:underline disabled:opacity-60"
                                      >
                                        {t('billing.invoiceByTransfer')}
                                      </button>
                                    )}
                                  </>
                                )
                              )}
                              <button
                                type="button"
                                onClick={() => openInvoice(invoice)}
                                className="text-sm font-medium text-brand-teal hover:underline"
                              >
                                {t('billing.downloadPdf')}
                              </button>
                            </span>
                          </Td>
                        </tr>
                        {credits.notes.length > 0 && (
                          <tr>
                            <td colSpan={5} className="px-4 pb-3 pt-0 border-b border-gray-100 bg-gray-50/60">
                              <ul className="pt-2 space-y-1.5" aria-label={t('billing.creditNotes')}>
                                {credits.notes.map((note) => (
                                  <li key={note.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-600">
                                    <span className="font-medium text-gray-800">
                                      {t('billing.creditNote', { number: note.number })}
                                    </span>
                                    <span>{day(note.issuedOn)}</span>
                                    <span className="tabular-nums font-medium text-gray-800">
                                      {'− '}{money(note.amount, note.currency)}
                                    </span>
                                    {note.reason && (
                                      <span
                                        className="min-w-0 max-w-full sm:max-w-xs truncate"
                                        title={t('billing.creditNoteReason', { reason: note.reason })}
                                      >
                                        {note.reason}
                                      </span>
                                    )}
                                    <button
                                      type="button"
                                      onClick={() => openCreditNote(note)}
                                      className="font-medium text-brand-teal hover:underline"
                                    >
                                      {t('billing.creditNoteDownload')}
                                    </button>
                                  </li>
                                ))}
                              </ul>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    )
                  })}
                </tbody>
              </TableWrap>
            )}
          </Card>
        </div>
      )}
    </>
  )
}
