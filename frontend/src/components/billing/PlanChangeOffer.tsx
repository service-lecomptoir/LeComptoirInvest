import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import {
  BILLING_ROUTES,
  USAGE_BAR,
  cardsOf,
  handedOutKey,
  offerView,
  requestablePlans,
  sentenceOf,
  usagePercent,
  usageTone,
  type Offer,
  type OfferPlan,
  type OfferRoutes,
  type Preview,
  type SaleTerms,
} from './planOffer'
import { PLAN_ACCENT, planHttp, usePlanWords } from './planOfferHost'
import { PlanBubble, PlanButton, PlanDialog, PlanSelect, PlanTextarea } from './planOfferKit'

/**
 * « Ma formule » on every « Mon abonnement » page: the plan, its quantity, its next payment,
 * then how to change it, drawn from ALICE'S offer.
 *
 * 🔴 ONE CARD, THE SAME IN EVERY PRODUCT. The owner, 12 Oct 2026, who did not see the plan
 * change aligned: « je ne le vois toujours pas ». Then, before two request buttons side by
 * side on a bespoke plan: « C'est quoi la différence entre les 2 ? ». This file and
 * `planOffer.ts` are copied unchanged in every product; `planOfferKit.tsx` lends the
 * product's own pieces, `planOfferHost.ts` its words and its server. The card has three
 * faces (`offerView`):
 *
 * - a catalogue plan: under « Changer de formule », the plans by price, the current one
 *   marked, « Choisir » opening the preview (prorata, VAT, next payment), then ONE request
 *   button, « Demander une offre sur mesure »;
 * - a bespoke, beta-tester or « sur devis » plan: the plan card carries ONE button,
 *   « Demander un changement », and the catalogue plans follow for comparison, each with
 *   « Demander ce changement »; the plan itself is not repeated as a card, no yellow box
 *   says it twice, no prorata is promised;
 * - nothing else published: the same single button and the sentence that says so.
 *
 * 🔴 NOTHING IS PRICED OR DECIDED HERE: the plans, their price before tax, the VAT, whether
 * a cap holds the account, how a plan is taken, the next payment, are Alice's answer.
 *
 * ⚠️ ONLY THE SUBSCRIBER ACTS (`can_change`, decided by this product's server): any other
 * account reads the same card without a button.
 */
export function PlanChangeOffer({
  saleTerms,
  blocked,
  limitLabel,
  usageLabel,
  onChanged,
  routes = BILLING_ROUTES,
  askTerms,
  badges,
  actions,
  notes,
  plansNote,
}: {
  /** The terms of sale ticked beside the plans (a plan taken is a sale), when owed. */
  saleTerms: SaleTerms
  /** True while the terms box is owed and unticked: no plan is taken. */
  blocked: boolean
  /** « Jusqu'à 10 dossiers », in this product's unit; null is unlimited. */
  limitLabel: (limit: number | null) => string
  /** « 12 biens gérés, sans limite », « 3 dossiers sur 10 »: what the account holds. */
  usageLabel: (count: number, limit: number | null) => string
  onChanged: () => void
  routes?: OfferRoutes
  /** A page that asks the terms of sale at the confirmation rather than beside the plans:
   *  the terms to send, `undefined` when none are owed, `null` when the reader declined. */
  askTerms?: () => Promise<SaleTerms | undefined>
  /** The page's own marks beside the plan's name (active, demo, to pay). */
  badges?: ReactNode
  /** The page's own buttons, on the card's row of actions (pay, portal, terminate). */
  actions?: ReactNode
  /** The page's own notices, under the plan (suspended, a transfer awaited). */
  notes?: ReactNode
  /** What the page asks before a plan is taken, above the cards (the terms of sale). */
  plansNote?: ReactNode
}) {
  const { t, language } = usePlanWords()
  const [offer, setOffer] = useState<Offer | null>(null)
  const [failed, setFailed] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)
  const [chosen, setChosen] = useState<OfferPlan | null>(null)
  const [asking, setAsking] = useState<{ planId: string } | null>(null)

  const amount = useCallback(
    (value: number, currency: string) => new Intl.NumberFormat(language, { style: 'currency', currency }).format(value),
    [language],
  )
  const day = useCallback(
    (iso: string) => new Intl.DateTimeFormat(language, { dateStyle: 'long' }).format(new Date(`${iso.slice(0, 10)}T12:00:00`)),
    [language],
  )

  const load = useCallback(() => {
    planHttp
      .get<Offer>(routes.offer)
      .then(data => {
        setOffer(data)
        setFailed(null)
      })
      // The server's sentence, or '' for the page's own (worded at render).
      .catch(error => setFailed(sentenceOf(error, '')))
  }, [routes.offer])

  useEffect(load, [load])

  if (failed !== null) return <section className={CARD}><p className="text-sm text-amber-800">{failed || t('unavailable')}</p></section>
  if (!offer) return <section className={CARD}><p className="text-sm text-gray-500">{t('loading')}</p></section>

  const view = offerView(offer)
  const current = offer.current
  const limit = current?.managed_limit ?? null
  const tone = usageTone(offer.managed_count, limit)
  const canAct = offer.can_change
  const details = (plan: OfferPlan) => planDetails(plan, t, amount)

  const cards = cardsOf(offer)

  return (
    <section className={CARD}>
      {/* ── The plan: its name never cut (« Bêta-test… » said nothing) ────────── */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium text-gray-500">{t('currentLabel')}</p>
          <p className="break-words text-lg font-semibold text-gray-900">{current?.name ?? t('noPlan')}</p>
          {current && current.price_ht > 0 && (
            <p className="flex flex-wrap items-baseline gap-x-1 text-sm text-gray-600">
              <span className="font-medium text-gray-900">{amount(current.price_ht, current.currency)}</span>
              <span className="text-xs text-gray-500">{t('perMonthSuffix')}</span>
              {details(current) && <PlanBubble label={t('detailsOf', { name: current.name })} text={details(current)} />}
            </p>
          )}
        </div>
        {badges && <div className="flex flex-wrap items-center gap-2">{badges}</div>}
      </div>
      {notes}

      {/* ── What the account holds: no bar without a ceiling, orange at it, red beyond ── */}
      <div>
        <p className="text-sm text-gray-700">{usageLabel(offer.managed_count, limit)}</p>
        {tone !== 'none' && (
          <div className="mt-1.5 h-2 w-full rounded-full bg-gray-100" aria-hidden="true">
            <div
              className={`h-2 rounded-full ${USAGE_BAR[tone]}`}
              style={{ width: `${usagePercent(offer.managed_count, limit)}%` }}
            />
          </div>
        )}
      </div>

      {offer.ends_on ? (
        <p className="text-sm text-amber-800">{t('endsOn', { day: day(offer.ends_on) })}</p>
      ) : offer.next_due_date ? (
        <p className="text-xs text-gray-500">{t('nextDue', { day: day(offer.next_due_date) })}</p>
      ) : null}

      {done && <p className="rounded-lg bg-green-50 px-3 py-2 text-sm text-green-800">{done}</p>}

      {/* ── The card's actions; a plan no click changes carries the ONE request here ── */}
      {(Boolean(actions) || view !== 'standard' || !canAct) && (
        <div>
          <div className="flex flex-wrap items-center gap-2">
            {actions}
            {view !== 'standard' && canAct && (
              <PlanButton
                onClick={() => {
                  setDone(null)
                  setAsking({ planId: '' })
                }}
              >
                {t('requestButton')}
              </PlanButton>
            )}
          </div>
          {view === 'frozen' && canAct && <p className="mt-1 text-xs text-gray-500">{t(handedOutKey(offer))}</p>}
          {view === 'empty' && canAct && <p className="mt-1 text-xs text-gray-500">{t('empty')}</p>}
          {!canAct && <p className="mt-1 text-xs text-gray-500">{t('readOnly')}</p>}
        </div>
      )}

      {/* ── The catalogue plans by price: to choose, or to compare and ask ───────── */}
      {view !== 'empty' && cards.length > 0 && (
        <div className="space-y-3 border-t border-gray-100 pt-4">
          <div className="flex items-center gap-1.5">
            <h3 className="text-sm font-semibold text-gray-900">{t('changePlan')}</h3>
            {view === 'standard' && offer.mode === 'change' && <PlanBubble label={t('changePlan')} text={t('info')} />}
          </div>
          {view === 'standard' && offer.mode === 'request' && <p className="text-xs text-gray-500">{t('noOnlinePayment')}</p>}
          {view === 'standard' && plansNote}
          <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {cards.map(plan => (
              <li
                key={plan.id}
                className={`flex min-w-0 flex-col gap-1 rounded-xl border p-3 ${
                  plan.is_current ? PLAN_ACCENT.card : 'border-gray-200'
                }`}
              >
                <p className="break-words text-sm font-semibold text-gray-900">{plan.name}</p>
                {plan.is_current && (
                  <span className={`w-fit rounded-full px-2 py-0.5 text-xs font-medium ${PLAN_ACCENT.badge}`}>
                    {t('current')}
                  </span>
                )}
                <p className="flex flex-wrap items-baseline gap-x-1">
                  <span className="whitespace-nowrap text-lg font-semibold text-gray-900">{amount(plan.price_ht, plan.currency)}</span>
                  <span className="whitespace-nowrap text-xs text-gray-500">{t('perMonthSuffix')}</span>
                </p>
                <p className="flex items-center gap-1 text-sm text-gray-600">
                  <span>{limitLabel(plan.managed_limit)}</span>
                  {details(plan) && <PlanBubble label={t('detailsOf', { name: plan.name })} text={details(plan)} />}
                </p>
                {plan.action === 'refused' && <p className="text-xs text-amber-800">{t('refusedShort')}</p>}
                {canAct && !plan.is_current && plan.action !== 'refused' && (
                  <div className="mt-auto pt-2">
                    <PlanButton
                      disabled={blocked && plan.action !== 'request'}
                      onClick={() => {
                        setDone(null)
                        if (plan.action === 'request') setAsking({ planId: plan.id })
                        else setChosen(plan)
                      }}
                    >
                      {plan.action === 'request' ? t('ask') : t('choose')}
                    </PlanButton>
                  </div>
                )}
              </li>
            ))}
          </ul>
          {view === 'standard' && canAct && (
            <div>
              <PlanButton
                onClick={() => {
                  setDone(null)
                  setAsking({ planId: '' })
                }}
              >
                {t('customButton')}
              </PlanButton>
              <p className="mt-1 text-xs text-gray-500">{t('customHelp')}</p>
            </div>
          )}
        </div>
      )}

      {chosen && (
        <ConfirmChange
          plan={chosen}
          saleTerms={saleTerms}
          amount={amount}
          day={day}
          routes={routes}
          askTerms={askTerms}
          onCancel={() => setChosen(null)}
          onDone={name => {
            setChosen(null)
            setDone(t('done', { name }))
            load()
            onChanged()
          }}
        />
      )}
      {asking && (
        <AskChange
          plans={requestablePlans(offer)}
          initial={asking.planId}
          frozen={view !== 'standard'}
          limitLabel={limitLabel}
          amount={amount}
          routes={routes}
          onCancel={() => setAsking(null)}
          onDone={() => {
            setAsking(null)
            setDone(t('requestSent'))
          }}
        />
      )}
    </section>
  )
}

const CARD = 'space-y-4 rounded-2xl border border-gray-200 bg-white p-4 sm:p-5'

/** What a card keeps for its ⓘ (the owner, 12 Oct 2026: name, price, cap on the card; the
 *  total with VAT, the overage and its effect on the account in the bubble). */
function planDetails(
  plan: OfferPlan,
  t: (key: string, vars?: Record<string, unknown>) => string,
  amount: (value: number, currency: string) => string,
): string {
  const lines: string[] = []
  if (plan.price_ttc !== null && plan.vat_rate !== null && plan.price_ht > 0) {
    lines.push(t('withTax', { amount: amount(plan.price_ttc, plan.currency), rate: plan.vat_rate }))
  }
  if (plan.overage_allowed && plan.overage_price) {
    lines.push(t('overage', { amount: amount(plan.overage_price, plan.currency) }))
  }
  if (plan.overage_count > 0) {
    lines.push(t('overageNow', { count: plan.overage_count, amount: amount(plan.overage_monthly, plan.currency) }))
  }
  if (plan.action === 'refused' && plan.refusal) {
    lines.push(t('refused', { count: plan.refusal.count, limit: plan.refusal.limit }))
  }
  return lines.join('\n')
}

function ConfirmChange({
  plan,
  saleTerms,
  amount,
  day,
  routes,
  askTerms,
  onCancel,
  onDone,
}: {
  plan: OfferPlan
  saleTerms: SaleTerms
  amount: (value: number, currency: string) => string
  day: (iso: string) => string
  routes: OfferRoutes
  askTerms?: () => Promise<SaleTerms | undefined>
  onCancel: () => void
  onDone: (name: string) => void
}) {
  const { t } = usePlanWords()
  const [preview, setPreview] = useState<Preview | null>(null)
  const [previewFailed, setPreviewFailed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  const [waiting, setWaiting] = useState(false)
  const safe = useRef<HTMLButtonElement | null>(null)

  useEffect(() => {
    safe.current?.focus()
    planHttp
      .post<Preview>(routes.preview, { plan_id: plan.id })
      .then(data => setPreview(data ?? {}))
      .catch(() => setPreviewFailed(true))
  }, [plan.id, routes.preview])

  const card = preview?.plan ?? plan
  const atPayment = (preview?.action ?? plan.action) === 'subscribe'
  const refusal = preview?.refusal ?? plan.refusal

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
      const data = await planHttp.post<{ url?: string; plan_name?: string }>(
        atPayment ? routes.checkout : routes.change,
        body,
      )
      if (data?.url) {
        window.location.href = data.url
        return
      }
      onDone(data?.plan_name ?? plan.name)
    } catch (error) {
      setProblem(sentenceOf(error, t('unavailable')))
      setBusy(false)
    }
  }

  if (waiting) return null
  return (
    <PlanDialog title={t('confirmTitle', { name: plan.name })} onCancel={onCancel}>
      <dl className="space-y-1 text-sm">
        <div className="flex justify-between gap-3">
          <dt className="text-gray-500">{t('monthly')}</dt>
          <dd className="text-right font-medium text-gray-900">{t('perMonth', { amount: amount(card.price_ht, card.currency) })}</dd>
        </div>
        {card.vat_rate !== null && card.price_ttc !== null && (
          <>
            <div className="flex justify-between gap-3">
              <dt className="text-gray-500">{t('vat', { rate: card.vat_rate })}</dt>
              <dd className="text-right font-medium text-gray-900">{amount(card.price_ttc - card.price_ht, card.currency)}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-gray-500">{t('total')}</dt>
              <dd className="text-right font-medium text-gray-900">{amount(card.price_ttc, card.currency)}</dd>
            </div>
          </>
        )}
      </dl>
      {card.overage_count > 0 && (
        <p className="text-xs text-gray-500">
          {t('overageNow', { count: card.overage_count, amount: amount(card.overage_monthly, card.currency) })}
        </p>
      )}
      {preview === null && !previewFailed && <p className="text-xs text-gray-500">{t('previewLoading')}</p>}
      {previewFailed && <p className="text-xs text-gray-500">{t('previewUnavailable')}</p>}
      {typeof preview?.proration_amount === 'number' && (
        <p className="text-sm text-gray-700">
          {preview.proration_amount >= 0
            ? t('prorataCharge', { amount: amount(preview.proration_amount, card.currency) })
            : t('prorataCredit', { amount: amount(Math.abs(preview.proration_amount), card.currency) })}
        </p>
      )}
      <p className="text-sm text-gray-700">{atPayment ? t('effectiveAtPayment') : t('effectiveNow')}</p>
      {preview?.next_billing_date && !atPayment && (
        <p className="text-xs text-gray-500">{t('nextBilling', { day: day(preview.next_billing_date) })}</p>
      )}
      {refusal && <p className="text-sm text-amber-800">{t('refused', { count: refusal.count, limit: refusal.limit })}</p>}
      {problem && <p role="alert" className="text-sm text-red-700">{problem}</p>}
      <div className="flex flex-wrap justify-end gap-2 pt-1">
        <PlanButton ref={safe} onClick={onCancel}>
          {t('cancel')}
        </PlanButton>
        <PlanButton tone="primary" disabled={busy || Boolean(refusal)} onClick={() => void submitChange()}>
          {atPayment ? t('pay') : t('confirm')}
        </PlanButton>
      </div>
    </PlanDialog>
  )
}

/**
 * The ONE request window, for both buttons: « Demander un changement » on a plan the team
 * hands out (the catalogue plans compared in its list), « Demander une offre sur mesure »
 * beside the cards. No plan chosen is the offer « sur mesure », said so to the team by Alice.
 */
function AskChange({
  plans,
  initial,
  frozen,
  limitLabel,
  amount,
  routes,
  onCancel,
  onDone,
}: {
  plans: OfferPlan[]
  initial: string
  frozen: boolean
  limitLabel: (limit: number | null) => string
  amount: (value: number, currency: string) => string
  routes: OfferRoutes
  onCancel: () => void
  onDone: () => void
}) {
  const { t } = usePlanWords()
  const [planId, setPlanId] = useState(initial)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)

  async function send() {
    setBusy(true)
    setProblem(null)
    try {
      await planHttp.post(routes.request, { plan_id: planId || null, message: message.trim() || null })
      onDone()
    } catch (error) {
      setProblem(sentenceOf(error, t('unavailable')))
      setBusy(false)
    }
  }

  return (
    <PlanDialog title={frozen || initial ? t('requestTitle') : t('customTitle')} onCancel={onCancel}>
      {plans.length > 0 && (
        <PlanSelect
          label={t('requestPlan')}
          hint={t('requestPlanHelp')}
          value={planId}
          onChange={setPlanId}
          options={[
            { value: '', label: t('requestPlanAny') },
            ...plans.map(plan => ({
              value: plan.id,
              label: `${plan.name} · ${t('perMonth', { amount: amount(plan.price_ht, plan.currency) })} · ${limitLabel(plan.managed_limit)}`,
            })),
          ]}
        />
      )}
      <PlanTextarea
        label={t('requestMessage')}
        hint={t('requestMessageHelp')}
        value={message}
        onChange={setMessage}
      />
      {problem && <p role="alert" className="text-sm text-red-700">{problem}</p>}
      <div className="flex flex-wrap justify-end gap-2 pt-1">
        <PlanButton onClick={onCancel}>{t('cancel')}</PlanButton>
        <PlanButton tone="primary" disabled={busy} onClick={() => void send()}>
          {t('requestSend')}
        </PlanButton>
      </div>
    </PlanDialog>
  )
}
