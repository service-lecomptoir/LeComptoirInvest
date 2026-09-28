import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Check, LogIn } from 'lucide-react'
import { publicApi, type PublicPlan } from '@/api'
import { money } from '@/lib/format'
import { usePlanPrice } from '@/lib/planPrice'
import { useAuthStore } from '@/store/authStore'
import { LogoMark } from '@/components/common/Logo'
import { LanguageSwitcher } from '@/components/common/LanguageSwitcher'
import { Card, Loading } from '@/components/common/Primitives'
import { SignupForm } from '@/components/signup/SignupForm'

/**
 * The public pricing page, identical to Le Comptoir RH's (the product owner, 28-29 Sept
 * 2026: « tarification est une page publique comme pour Immo »): the catalogue plans the
 * console sells for Invest, each with its ceiling of investors and what one more costs, and
 * the sign-up right under the plan chosen.
 *
 * ⚠️ THE PRICES ARE THE CONSOLE'S, read at each visit (`GET /public/plans`), never written
 * here: a price changed in Alice is the price shown, the day it changes.
 *
 * 🔴 ONLY THE CATALOGUE IS PUBLIC (« seules les offres catalogues sont publiques »). An
 * offer for a management company is made for that company, in Alice, after a
 * conversation: it is never a card here. The page says a quotation exists, in one line, and
 * that line opens the same form, quoted.
 */
export default function Pricing() {
  const { t, i18n } = useTranslation()
  const planPrice = usePlanPrice()
  const signedIn = useAuthStore((s) => s.isAuthenticated)
  const [plans, setPlans] = useState<PublicPlan[] | null>(null)
  // A plan's id, or « quote » for the quotation the line below the plans opens.
  const [chosen, setChosen] = useState<string | null>(null)
  const form = useRef<HTMLDivElement | null>(null)

  // ⚠️ OUTSIDE THE SHELL, like the sign-in page: it names its own tab.
  useEffect(() => {
    document.title = `Le Comptoir Invest | ${t('pricing.title')}`
  }, [t, i18n.language])

  useEffect(() => {
    publicApi
      .plans()
      .then(({ data }) => setPlans((Array.isArray(data) ? data : []).filter((plan) => !plan.sur_devis)))
      .catch(() => setPlans([]))
  }, [])

  useEffect(() => {
    if (chosen !== null) form.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [chosen])

  const facts = [t('pricing.fact1'), t('pricing.fact2'), t('pricing.fact3')]

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-brand-navy text-white">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-3">
          <Link to={signedIn ? '/' : '/login'} className="flex min-w-0 items-center gap-2">
            <LogoMark size={30} className="shrink-0 rounded-md ring-1 ring-white/25 text-brand-teal" />
            <span className="truncate text-base font-semibold tracking-tight">
              {t('brand.first')} <span className="text-brand-teal">{t('brand.second')}</span>
            </span>
          </Link>
          <span className="flex-1" />
          <LanguageSwitcher dark />
          {!signedIn && (
            <Link
              to="/login"
              className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-white/25 px-3 py-1.5 text-sm hover:bg-white/10"
            >
              <LogIn size={15} />
              <span className="hidden sm:inline">{t('pricing.signIn')}</span>
              <span className="sr-only sm:hidden">{t('pricing.signIn')}</span>
            </Link>
          )}
        </div>
      </header>

      <main className="mx-auto max-w-6xl space-y-8 px-4 py-10">
        <section className="text-center">
          <h1 className="text-2xl font-bold text-brand-navy sm:text-3xl">{t('pricing.headline')}</h1>
          <p className="mx-auto mt-2 max-w-2xl text-sm text-gray-600 sm:text-base">{t('pricing.lead')}</p>
        </section>

        {plans === null ? (
          <Loading label={t('common.loading')} />
        ) : plans.length === 0 ? (
          <Card className="p-6 text-center text-sm text-gray-600">{t('pricing.none')}</Card>
        ) : (
          <section
            className={`grid gap-x-4 gap-y-6 pt-2 sm:grid-cols-2 ${plans.length >= 4 ? 'lg:grid-cols-4' : plans.length === 3 ? 'lg:grid-cols-3' : 'lg:mx-auto lg:max-w-3xl'}`}
          >
            {plans.map((plan, index) => {
              const featured = index === 1
              return (
                <div
                  key={plan.id}
                  className={`relative flex flex-col rounded-2xl border bg-white p-5 shadow-sm ${featured ? 'border-brand-navy ring-2 ring-brand-navy/20' : 'border-gray-200'}`}
                >
                  {featured && (
                    <span className="absolute -top-3 left-5 rounded-full bg-brand-teal px-2.5 py-0.5 text-xs font-semibold text-white">
                      {t('pricing.popular')}
                    </span>
                  )}
                  <h2 className="text-lg font-semibold text-brand-navy">{plan.name}</h2>
                  <p className="mt-2 text-2xl font-bold text-gray-900">{planPrice(plan)}</p>
                  {plan.monthly_price > 0 && (
                    <p className="text-xs text-gray-500">{t('pricing.excludingTax', { rate: plan.tva_rate })}</p>
                  )}
                  <ul className="mt-4 flex-1 space-y-2 text-sm text-gray-700">
                    <li className="flex gap-2">
                      <Check size={16} className="mt-0.5 shrink-0 text-brand-teal" />
                      {plan.investor_limit
                        ? t('pricing.upTo', { count: plan.investor_limit })
                        : t('pricing.unlimited')}
                    </li>
                    {plan.overage_price > 0 && (
                      <li className="flex gap-2">
                        <Check size={16} className="mt-0.5 shrink-0 text-brand-teal" />
                        {t('pricing.overage', { amount: money(plan.overage_price, 'EUR') })}
                      </li>
                    )}
                    {plan.description && (
                      <li className="flex gap-2">
                        <Check size={16} className="mt-0.5 shrink-0 text-brand-teal" />
                        <span className="min-w-0 break-words">{plan.description}</span>
                      </li>
                    )}
                  </ul>
                  <button
                    type="button"
                    onClick={() => setChosen(plan.id)}
                    className={`mt-5 rounded-lg px-4 py-2 text-sm font-semibold ${featured ? 'bg-brand-navy text-white hover:bg-brand-navy-light' : 'border border-brand-navy/40 text-brand-navy hover:bg-brand-navy/5'}`}
                  >
                    {t('pricing.choose')}
                  </button>
                </div>
              )
            })}
          </section>
        )}

        <p className="text-center text-sm text-gray-600">
          {t('pricing.forClients')}{' '}
          <button type="button" onClick={() => setChosen('quote')} className="font-semibold text-brand-navy underline">
            {t('pricing.askQuote')}
          </button>
        </p>

        <section className="grid gap-3 text-sm text-gray-600 sm:grid-cols-3">
          {facts.map((fact) => (
            <p key={fact} className="flex gap-2">
              <Check size={16} className="mt-0.5 shrink-0 text-brand-navy" />
              {fact}
            </p>
          ))}
        </section>

        {chosen !== null && (
          <div ref={form} className="mx-auto max-w-xl scroll-mt-6">
            <Card className="space-y-3 p-5 sm:p-6">
              <h2 className="text-base font-semibold text-gray-900">
                {chosen === 'quote' ? t('signup.quoteTitle') : t('signup.title')}
              </h2>
              <SignupForm key={chosen} initialPlanId={chosen === 'quote' ? '' : chosen} quote={chosen === 'quote'} />
            </Card>
          </div>
        )}
      </main>
      <footer className="mx-auto max-w-6xl px-4 pb-8 text-xs text-gray-400">
        © {new Date().getFullYear()} {t('brand.full')}
      </footer>
    </div>
  )
}
