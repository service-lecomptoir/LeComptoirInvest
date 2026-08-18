import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { CreditCard, Landmark, ExternalLink, FileText, Check } from 'lucide-react'
import { billingApi } from '@/api'
import { apiClient } from '@/api/client'
import { Button, Badge } from '@/components/ui'
import {
  Card, EmptyState, Loading, Notice, PageHeader, Pill, TableWrap, Td, Th,
} from '@/components/common/Primitives'
import { confirmDialog } from '@/store/confirm'
import { toast } from '@/store/toast'
import { money, day } from '@/lib/format'
import type {
  BillingInvoice, BillingPlan, BillingStatus, BillingSubscription, PaymentMethods,
} from '@/types'

/**
 * Ce que le gestionnaire paie pour utiliser ce produit, et par quels moyens.
 *
 * 🔴 CET ÉCRAN NE PARLE PAS DES SOUSCRIPTIONS AUX FONDS. Le mot « souscription » appartient
 * au métier ici, et l'écran voisin le porte déjà. Confondre les deux dans un produit dont
 * la matière est l'argent des autres serait la pire des économies de vocabulaire.
 *
 * 🔴 AUCUN PRIX N'EST ÉCRIT ICI. Les offres, les montants et l'état de l'abonnement
 * viennent de la console : cet écran les affiche et déclenche des actions, il n'en décide
 * aucune. Une valeur en dur y deviendrait une deuxième vérité que personne ne penserait à
 * mettre à jour le jour d'un changement de tarif.
 *
 * ⚠️ « JE NE SAIS PAS » N'EST PAS « C'EST GRATUIT ». Quand la console ne répond pas, ou
 * qu'aucune ne pilote l'instance, l'écran le dit franchement. Afficher un abonnement vide
 * à 0 € laisserait croire à un droit que personne n'a accordé.
 */
export default function Billing() {
  const { t } = useTranslation()
  const [subscription, setSubscription] = useState<BillingSubscription | null>(null)
  const [methods, setMethods] = useState<PaymentMethods | null>(null)
  const [status, setStatus] = useState<BillingStatus | null>(null)
  const [plans, setPlans] = useState<BillingPlan[]>([])
  const [invoices, setInvoices] = useState<BillingInvoice[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<string | null>(null)
  const [refusal, setRefusal] = useState<string | null>(null)

  // 🔴 C'EST ICI QUE STRIPE RENVOIE LE PAYEUR, et l'écran doit le reconnaître. Sans cela,
  // un gestionnaire qui vient de payer revient sur une page identique à celle qu'il a
  // quittée : rien ne lui dit que son paiement est passé, et le premier réflexe est de
  // repayer. Le paramètre est retiré de l'adresse aussitôt lu, pour qu'un rafraîchissement
  // ne rejoue pas le message.
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
    // Appels indépendants : une facture illisible ne doit pas emporter l'offre en cours,
    // et une console partiellement disponible vaut mieux qu'un écran blanc.
    Promise.allSettled([
      billingApi.mine(),
      billingApi.paymentMethods(),
      billingApi.status(),
      billingApi.plans(),
      billingApi.invoices(),
    ]).then(([s, m, st, p, i]) => {
      if (s.status === 'fulfilled') setSubscription(s.value.data)
      if (m.status === 'fulfilled') setMethods(m.value.data)
      if (st.status === 'fulfilled') setStatus(st.value.data)
      if (p.status === 'fulfilled') setPlans(p.value.data)
      if (i.status === 'fulfilled') setInvoices(i.value.data)
      setLoading(false)
    })
  }
  useEffect(load, [])

  const refusalOf = (error: unknown): string => {
    const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
    return typeof detail === 'string' ? detail : t('billing.unavailable')
  }

  /** Ouvre la page de paiement dans le même onglet : on quitte le produit le temps de payer. */
  const goToPayment = async (planId?: string) => {
    setBusy('checkout')
    setRefusal(null)
    try {
      const { data } = await billingApi.checkout(planId)
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

  const changePlan = async (plan: BillingPlan) => {
    // L'estimation au prorata est demandée AVANT la question : confirmer un changement
    // d'offre sans savoir ce qu'il coûte aujourd'hui, ce n'est pas confirmer.
    let estimate = ''
    try {
      const { data } = await billingApi.previewChange(plan.id)
      if (data?.amount_due != null) {
        estimate = t('billing.prorationEstimate', {
          amount: money(data.amount_due, data.currency || 'eur'),
        })
      }
    } catch {
      /* une estimation absente n'empêche pas de changer d'offre */
    }
    const confirmed = await confirmDialog({
      title: t('billing.changeTitle', { plan: plan.name }),
      message: `${t('billing.changeMessage', {
        plan: plan.name,
        price: money(plan.monthly_price, methods?.currency || 'eur'),
      })}${estimate ? ` ${estimate}` : ''}`,
      confirmLabel: t('billing.changeConfirm'),
    })
    if (!confirmed) return
    setBusy(plan.id)
    setRefusal(null)
    try {
      await billingApi.changePlan(plan.id)
      toast.success(t('billing.changed'))
      load()
    } catch (error) {
      setRefusal(refusalOf(error))
    } finally {
      setBusy(null)
    }
  }

  /** Le PDF passe par le client authentifié : une adresse nue rendrait un 401. */
  const openInvoice = async (invoice: BillingInvoice) => {
    try {
      const response = await apiClient.get(billingApi.invoicePdfUrl(invoice.id), {
        responseType: 'blob',
        skipErrorToast: true,
      })
      const url = URL.createObjectURL(response.data as Blob)
      window.open(url, '_blank', 'noopener')
      // Libéré au tour suivant : révoquer tout de suite couperait l'ouverture.
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

          {/* ── L'offre en cours ──────────────────────────────────────────────── */}
          <Card>
            <div className="p-5 sm:p-6">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-xs uppercase tracking-wide text-gray-500">
                    {t('billing.currentPlan')}
                  </p>
                  <p className="mt-1 text-xl font-semibold text-gray-900">
                    {current?.plan_name || t('billing.noPlan')}
                  </p>
                  {current?.monthly_price != null && (
                    <p className="mt-0.5 text-sm text-gray-600">
                      {t('billing.perMonth', { price: money(current.monthly_price, currency) })}
                    </p>
                  )}
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {current?.fund_limit != null && (
                    <Pill tone="info">{t('billing.fundLimit', { count: current.fund_limit })}</Pill>
                  )}
                  {status?.has_subscription ? (
                    <Badge variant="green">{t('billing.active')}</Badge>
                  ) : (
                    <Badge variant="gray">{t('billing.notSubscribed')}</Badge>
                  )}
                </div>
              </div>

              {status?.current_period_end && (
                <p className="mt-4 text-sm text-gray-600">
                  {status.cancel_at_period_end
                    ? t('billing.endsOn', { date: day(status.current_period_end) })
                    : t('billing.renewsOn', { date: day(status.current_period_end) })}
                </p>
              )}
              {current?.access_until && (
                <p className="mt-1 text-sm text-gray-600">
                  {t('billing.accessUntil', { date: day(current.access_until) })}
                </p>
              )}
            </div>
          </Card>

          {/* ── Les moyens de paiement ────────────────────────────────────────── */}
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
              {/* L'aide vit SOUS la rangée, jamais dans une cellule alignée en bas. */}
              <p className="mt-4 text-xs text-gray-500">{t('billing.methodsHint')}</p>
            </div>
          </Card>

          {/* ── Les offres ────────────────────────────────────────────────────── */}
          {plans.length > 0 && (
            <Card>
              <div className="p-5 sm:p-6 pb-3">
                <h2 className="text-sm font-semibold text-gray-900">{t('billing.offers')}</h2>
              </div>
              <div className="px-5 sm:px-6 pb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {plans.map((plan) => {
                  const isCurrent = plan.name === current?.plan_name
                  return (
                    <div
                      key={plan.id}
                      className={`rounded-xl border p-4 flex flex-col ${
                        isCurrent ? 'border-brand-teal bg-brand-teal/5' : 'border-gray-200'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-sm font-semibold text-gray-900">{plan.name}</p>
                        {isCurrent && (
                          <span className="inline-flex items-center gap-1 text-xs font-medium text-brand-teal">
                            <Check size={13} /> {t('billing.yourPlan')}
                          </span>
                        )}
                      </div>
                      <p className="mt-1 text-lg font-semibold text-gray-900">
                        {money(plan.monthly_price, currency)}
                        <span className="text-sm font-normal text-gray-500"> {t('billing.monthSuffix')}</span>
                      </p>
                      <p className="mt-1 text-sm text-gray-600 flex-1">
                        {plan.property_limit != null
                          ? t('billing.fundLimit', { count: plan.property_limit })
                          : t('billing.unlimitedFunds')}
                      </p>
                      {!isCurrent && (
                        <Button
                          variant="secondary"
                          className="mt-4"
                          disabled={busy === plan.id}
                          onClick={() =>
                            status?.has_subscription ? changePlan(plan) : goToPayment(plan.id)
                          }
                        >
                          {status?.has_subscription ? t('billing.switchTo') : t('billing.subscribe')}
                        </Button>
                      )}
                    </div>
                  )
                })}
              </div>
            </Card>
          )}

          {/* ── Les factures ──────────────────────────────────────────────────── */}
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
