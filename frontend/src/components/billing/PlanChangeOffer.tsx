import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import { Check, Info } from 'lucide-react'
import { apiClient } from '@/api/client'
import {
  BILLING_ROUTES,
  handedOutKey,
  sentenceOf,
  type Offer,
  type OfferPlan,
  type OfferRoutes,
  type Preview,
  type SaleTerms,
} from './planOffer'

/**
 * The plans of THIS product as cards, and the change of plan, drawn from ALICE'S offer
 * (the owner, 11 Oct 2026: a plan change as on Le Comptoir Immo, in every product).
 *
 * 🔴 NOTHING IS PRICED OR DECIDED HERE. Which plans, their price before tax, the VAT of the
 * subscriber's territory, whether a cap holds what the account already has, how a plan is
 * taken (a Stripe change, a Checkout, a request to the team): each is Alice's answer
 * (`GET /billing/offer`, her `services/plan_change.py`). The same component is drawn in
 * every product; a rule copied here would be the next offer that disagrees with the bill.
 *
 * ⚠️ ONLY THE SUBSCRIBER ACTS (`can_change`, decided by this product's server): any other
 * account reads the same cards without a button.
 */

const QUIET =
  'inline-flex items-center justify-center rounded-lg border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50'
const PRIMARY =
  'inline-flex items-center justify-center rounded-lg bg-brand-navy px-3 py-1.5 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50'
const FIELD = 'mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm'

export function PlanChangeOffer({
  saleTerms,
  blocked,
  limitLabel,
  onChanged,
  routes = BILLING_ROUTES,
  askTerms,
}: {
  /** The terms of sale ticked beside the plans (a plan taken is a sale), when owed. */
  saleTerms: SaleTerms
  /** True while the terms box is owed and unticked: no plan is taken. */
  blocked: boolean
  /** « Jusqu'à 10 dossiers », in this product's unit; null is unlimited. */
  limitLabel: (limit: number | null) => string
  onChanged: () => void
  routes?: OfferRoutes
  /** A page that asks the terms of sale at the confirmation rather than beside the plans:
   *  the terms to send, `undefined` when none are owed, `null` when the reader declined. */
  askTerms?: () => Promise<SaleTerms | undefined>
}) {
  const { t, i18n } = useTranslation()
  const [offer, setOffer] = useState<Offer | null>(null)
  const [failed, setFailed] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)
  const [chosen, setChosen] = useState<OfferPlan | null>(null)
  const [asking, setAsking] = useState(false)

  const amount = useCallback(
    (value: number, currency: string) =>
      new Intl.NumberFormat(i18n.language, { style: 'currency', currency }).format(value),
    [i18n.language],
  )

  const load = useCallback(() => {
    apiClient
      .get<Offer>(routes.offer, { skipErrorToast: true })
      .then(({ data }) => {
        setOffer(data)
        setFailed(null)
      })
      .catch(error => setFailed(sentenceOf(error, t('planChange.unavailable'))))
  }, [t, routes.offer])

  useEffect(load, [load])

  if (failed) return <p className="text-sm text-amber-800">{failed}</p>
  if (!offer) return <p className="text-sm text-gray-500">{t('planChange.loading')}</p>

  const handedOut = handedOutKey(offer)
  const others = offer.plans.filter(plan => !plan.is_current)
  const cards = [...(offer.current ? [offer.current] : []), ...others]
  const canAct = offer.can_change && offer.self_service

  return (
    <div className="space-y-3">
      {done && <p className="rounded-lg bg-green-50 px-3 py-2 text-sm text-green-800">{done}</p>}
      {handedOut && (
        <div className="space-y-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
          <p className="text-sm text-amber-900">{t(handedOut)}</p>
          {offer.can_change && (
            <>
              <button type="button" className={QUIET} onClick={() => setAsking(true)}>
                {t('planChange.requestButton')}
              </button>
              <p className="text-xs text-amber-800">{t('planChange.handedOutHelp')}</p>
            </>
          )}
        </div>
      )}
      {!offer.can_change && <p className="text-xs text-gray-500">{t('planChange.readOnly')}</p>}
      {others.length === 0 ? (
        <p className="text-sm text-gray-500">{t('planChange.none')}</p>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {cards.map(plan => (
            <li
              key={plan.id}
              className={`flex flex-col gap-1.5 rounded-xl border p-4 ${
                plan.is_current ? 'border-brand-teal bg-brand-teal/5' : 'border-gray-200'
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <p className="text-sm font-semibold text-gray-900">{plan.name}</p>
                {plan.is_current && (
                  <span className="inline-flex items-center gap-1 text-xs font-medium text-brand-teal">
                    <Check size={13} /> {t('planChange.current')}
                  </span>
                )}
              </div>
              <p className="text-lg font-semibold text-gray-900">
                {t('planChange.perMonth', { amount: amount(plan.price_ht, plan.currency) })}
              </p>
              {plan.price_ttc !== null && plan.vat_rate !== null && plan.price_ht > 0 && (
                <p className="text-xs text-gray-500">
                  {t('planChange.withTax', { amount: amount(plan.price_ttc, plan.currency), rate: plan.vat_rate })}
                </p>
              )}
              <p className="text-sm text-gray-600">{limitLabel(plan.managed_limit)}</p>
              {plan.overage_allowed && plan.overage_price ? (
                <p className="text-xs text-gray-500">
                  {t('planChange.overage', { amount: amount(plan.overage_price, plan.currency) })}
                </p>
              ) : null}
              {plan.overage_count > 0 && (
                <p className="text-xs text-gray-500">
                  {t('planChange.overageNow', {
                    count: plan.overage_count,
                    amount: amount(plan.overage_monthly, plan.currency),
                  })}
                </p>
              )}
              {plan.action === 'refused' && plan.refusal && (
                <p className="text-xs text-amber-800">
                  {t('planChange.refused', { count: plan.refusal.count, limit: plan.refusal.limit })}
                </p>
              )}
              {canAct && !plan.is_current && plan.action !== 'refused' && (
                <div className="mt-auto pt-2">
                  <button
                    type="button"
                    className={QUIET}
                    disabled={blocked && plan.action !== 'request'}
                    onClick={() => {
                      setDone(null)
                      if (plan.action === 'request') setAsking(true)
                      else setChosen(plan)
                    }}
                  >
                    {plan.action === 'request' ? t('planChange.ask') : t('planChange.choose')}
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      <p className="flex items-start gap-1 text-xs text-gray-500">
        <Info size={13} className="mt-0.5 shrink-0" aria-hidden="true" />
        {t('planChange.info')}
      </p>
      {chosen && (
        <ConfirmChange
          plan={chosen}
          saleTerms={saleTerms}
          amount={amount}
          routes={routes}
          askTerms={askTerms}
          onCancel={() => setChosen(null)}
          onDone={name => {
            setChosen(null)
            setDone(t('planChange.done', { name }))
            load()
            onChanged()
          }}
        />
      )}
      {asking && (
        <AskChange
          plans={others}
          routes={routes}
          onCancel={() => setAsking(false)}
          onDone={() => {
            setAsking(false)
            setDone(t('planChange.requestSent'))
          }}
        />
      )}
    </div>
  )
}

/**
 * A dialog of the house: Escape closes it, an outside click does not (a stray click is not
 * an answer), the focus starts on the safe button.
 */
function Dialog({ title, onCancel, children }: { title: string; onCancel: () => void; children: ReactNode }) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCancel()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onCancel])
  return createPortal(
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/30 px-4" role="dialog" aria-modal="true" aria-label={title}>
      <div className="max-h-[90dvh] w-full max-w-md space-y-3 overflow-y-auto rounded-xl bg-white p-5 shadow-lg">
        <p className="text-base font-semibold text-gray-900">{title}</p>
        {children}
      </div>
    </div>,
    document.body,
  )
}

function ConfirmChange({
  plan,
  saleTerms,
  amount,
  routes,
  askTerms,
  onCancel,
  onDone,
}: {
  plan: OfferPlan
  saleTerms: SaleTerms
  amount: (value: number, currency: string) => string
  routes: OfferRoutes
  askTerms?: () => Promise<SaleTerms | undefined>
  onCancel: () => void
  onDone: (name: string) => void
}) {
  const { t, i18n } = useTranslation()
  const [preview, setPreview] = useState<Preview | null>(null)
  const [previewFailed, setPreviewFailed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  const [waiting, setWaiting] = useState(false)
  const safe = useRef<HTMLButtonElement | null>(null)

  useEffect(() => {
    safe.current?.focus()
    apiClient
      .post<Preview>(routes.preview, { plan_id: plan.id }, { skipErrorToast: true })
      .then(({ data }) => setPreview(data ?? {}))
      .catch(() => setPreviewFailed(true))
  }, [plan.id, routes.preview])

  const card = preview?.plan ?? plan
  const atPayment = (preview?.action ?? plan.action) === 'subscribe'
  const refusal = preview?.refusal ?? plan.refusal
  const day = (iso: string) => new Intl.DateTimeFormat(i18n.language, { dateStyle: 'long' }).format(new Date(`${iso}T12:00:00`))

  async function submitChange() {
    setBusy(true)
    setProblem(null)
    try {
      // The terms ticked travel both ways the products read them (nested or flat).
      // The page's own terms dialog is shown alone, this one hidden behind nothing.
      setWaiting(true)
      const asked = askTerms ? await askTerms() : undefined
      setWaiting(false)
      if (asked === null) {
        setBusy(false)
        return
      }
      const ticked = asked || saleTerms || undefined
      const body = { plan_id: plan.id, terms: ticked, cgv: ticked?.cgv, language: ticked?.language }
      const { data } = await apiClient.post<{ url?: string; plan_name?: string }>(
        atPayment ? routes.checkout : routes.change,
        body,
        { skipErrorToast: true },
      )
      if (data?.url) {
        window.location.href = data.url
        return
      }
      onDone(data?.plan_name ?? plan.name)
    } catch (error) {
      setProblem(sentenceOf(error, t('planChange.unavailable')))
      setBusy(false)
    }
  }

  if (waiting) return null
  return (
    <Dialog title={t('planChange.confirmTitle', { name: plan.name })} onCancel={onCancel}>
      <dl className="space-y-1 text-sm">
        <div className="flex justify-between gap-3">
          <dt className="text-gray-500">{t('planChange.monthly')}</dt>
          <dd className="font-medium text-gray-900">{t('planChange.perMonth', { amount: amount(card.price_ht, card.currency) })}</dd>
        </div>
        {card.vat_rate !== null && card.price_ttc !== null && (
          <>
            <div className="flex justify-between gap-3">
              <dt className="text-gray-500">{t('planChange.vat', { rate: card.vat_rate })}</dt>
              <dd className="font-medium text-gray-900">{amount(card.price_ttc - card.price_ht, card.currency)}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-gray-500">{t('planChange.total')}</dt>
              <dd className="font-medium text-gray-900">{amount(card.price_ttc, card.currency)}</dd>
            </div>
          </>
        )}
      </dl>
      {preview === null && !previewFailed && <p className="text-xs text-gray-500">{t('planChange.previewLoading')}</p>}
      {previewFailed && <p className="text-xs text-gray-500">{t('planChange.previewUnavailable')}</p>}
      {typeof preview?.proration_amount === 'number' && (
        <p className="text-sm text-gray-700">
          {preview.proration_amount >= 0
            ? t('planChange.prorataCharge', { amount: amount(preview.proration_amount, card.currency) })
            : t('planChange.prorataCredit', { amount: amount(Math.abs(preview.proration_amount), card.currency) })}
        </p>
      )}
      <p className="text-sm text-gray-700">{atPayment ? t('planChange.effectiveAtPayment') : t('planChange.effectiveNow')}</p>
      {preview?.next_billing_date && !atPayment && (
        <p className="text-xs text-gray-500">{t('planChange.nextBilling', { day: day(preview.next_billing_date) })}</p>
      )}
      {refusal && (
        <p className="text-sm text-amber-800">
          {t('planChange.refused', { count: refusal.count, limit: refusal.limit })}
        </p>
      )}
      {problem && <p role="alert" className="text-sm text-red-700">{problem}</p>}
      <div className="flex flex-wrap justify-end gap-2 pt-1">
        <button ref={safe} type="button" className={QUIET} onClick={onCancel}>
          {t('planChange.cancel')}
        </button>
        <button type="button" className={PRIMARY} disabled={busy || Boolean(refusal)} onClick={() => void submitChange()}>
          {atPayment ? t('planChange.pay') : t('planChange.confirm')}
        </button>
      </div>
    </Dialog>
  )
}

function AskChange({
  plans,
  routes,
  onCancel,
  onDone,
}: {
  plans: OfferPlan[]
  routes: OfferRoutes
  onCancel: () => void
  onDone: () => void
}) {
  const { t } = useTranslation()
  const [planId, setPlanId] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)

  async function send() {
    setBusy(true)
    setProblem(null)
    try {
      await apiClient.post(
        routes.request,
        { plan_id: planId || null, message: message.trim() || null },
        { skipErrorToast: true },
      )
      onDone()
    } catch (error) {
      setProblem(sentenceOf(error, t('planChange.unavailable')))
      setBusy(false)
    }
  }

  return (
    <Dialog title={t('planChange.requestTitle')} onCancel={onCancel}>
      <div>
        <label className="block text-xs font-medium text-gray-600">
          {t('planChange.requestPlan')}
          <select className={FIELD} value={planId} onChange={event => setPlanId(event.target.value)}>
            <option value="">{t('planChange.requestPlanAny')}</option>
            {plans.map(plan => (
              <option key={plan.id} value={plan.id}>
                {plan.name}
              </option>
            ))}
          </select>
        </label>
        <p className="mt-1 text-xs text-gray-500">{t('planChange.requestPlanHelp')}</p>
      </div>
      <div>
        <label className="block text-xs font-medium text-gray-600">
          {t('planChange.requestMessage')}
          <textarea className={FIELD} rows={3} maxLength={2000} value={message} onChange={event => setMessage(event.target.value)} />
        </label>
        <p className="mt-1 text-xs text-gray-500">{t('planChange.requestMessageHelp')}</p>
      </div>
      {problem && <p role="alert" className="text-sm text-red-700">{problem}</p>}
      <div className="flex flex-wrap justify-end gap-2 pt-1">
        <button type="button" className={QUIET} onClick={onCancel}>
          {t('planChange.cancel')}
        </button>
        <button type="button" className={PRIMARY} disabled={busy} onClick={() => void send()}>
          {t('planChange.requestSend')}
        </button>
      </div>
    </Dialog>
  )
}
