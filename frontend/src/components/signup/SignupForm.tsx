import { useEffect, useId, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AlertTriangle, CheckCircle2, Mail } from 'lucide-react'
import { publicApi, type Country, type PublicPlan, type SignupOutcome } from '@/api'
import { errorMessage } from '@/api/client'
import { usePlanPrice } from '@/lib/planPrice'
import { checkSirenSiret } from '@/lib/siret'
import { offersRetry, outcomeTitleKey, outcomeTone } from '@/lib/signupOutcome'
import { AddressAutocomplete } from '@/components/common/AddressAutocomplete'
import { SiretInput } from '@/components/common/SiretInput'
import { Button, Field, Input, Select, inputBaseClass } from '@/components/ui'

const FRANCE: Country = { code: 'FR', name: 'France', number_label: 'SIREN / SIRET' }

/** The two profiles, in the words this product stores for an account (`account_kind`). */
const SINGLE_FUND = 'single_fund'
const MANAGEMENT_COMPANY = 'management_company'
/** The console's two words for whose name the account bears (`owner_kind`). */
const PERSON = 'personne'
const COMPANY = 'societe'

/**
 * The sign-up with a plan, identical to Le Comptoir RH (the product owner, 28-29 Sept
 * 2026): the prospect chooses a catalogue plan and says who they are; the console sends a
 * confirmation e-mail, and the click in it creates the account and sends the credentials.
 * A management company running several vehicles for clients asks for a quotation instead.
 *
 * ⚠️ WHAT FOLLOWS IS SAID FROM THE CONSOLE'S ANSWER, never assumed: an e-mail sent, an
 * account that already exists (with the way to it), or a request an operator will answer.
 */
export function SignupForm({
  initialPlanId = '',
  quote = false,
  onBack,
}: {
  initialPlanId?: string
  /** Opened from « Demandez un devis »: the requester manages several vehicles. */
  quote?: boolean
  onBack?: () => void
}) {
  const { t } = useTranslation()
  const planPrice = usePlanPrice()
  const uid = useId()
  const [plans, setPlans] = useState<PublicPlan[] | null>(null)
  const [draft, setDraft] = useState({
    profile: quote ? MANAGEMENT_COMPANY : SINGLE_FUND,
    requester_kind: COMPANY,
    plan_id: initialPlanId,
    first_name: '',
    last_name: '',
    email: '',
    company: '',
    company_number: '',
    phone: '',
    street: '',
    zip_code: '',
    city: '',
    region: '',
    country: 'FR',
    message: '',
  })
  const [countries, setCountries] = useState<Country[]>([FRANCE])
  const [problem, setProblem] = useState<string | null>(null)
  const problemBox = useRef<HTMLParagraphElement | null>(null)
  const outcomeBox = useRef<HTMLDivElement | null>(null)
  const [busy, setBusy] = useState(false)
  const [outcome, setOutcome] = useState<SignupOutcome | null>(null)
  const set = (patch: Partial<typeof draft>) => setDraft((d) => ({ ...d, ...patch }))

  useEffect(() => {
    publicApi
      .plans()
      .then(({ data }) => setPlans(Array.isArray(data) ? data : []))
      .catch(() => setPlans([]))
  }, [])

  useEffect(() => {
    publicApi
      .countries()
      .then(({ data }) => {
        if (Array.isArray(data) && data.length) setCountries(data)
      })
      .catch(() => undefined)
  }, [])

  // ⚠️ THE REFUSAL IS AT THE TOP OF A LONG FORM: on a telephone the button that sent it is
  // a full screen below, and a sentence nobody scrolls up to is a refusal never read.
  useEffect(() => {
    if (problem) problemBox.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [problem])

  // ⚠️ AND THE ANSWER REPLACES A FORM TWO SCREENS LONG: on a telephone it lands below the
  // fold, and the reader is left looking at the plans with no idea it was sent.
  useEffect(() => {
    if (outcome) outcomeBox.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [outcome])

  const country = countries.find((c) => c.code === draft.country) ?? FRANCE
  const inFrance = country.code === 'FR'
  // 🔴 ONLY THE CATALOGUE: a quoted offer is made for one customer, never picked here.
  const catalogue = (plans ?? []).filter((p) => !p.sur_devis)
  const quoted = draft.profile === MANAGEMENT_COMPANY
  const isCompany = draft.requester_kind === COMPANY

  async function send(event: React.FormEvent) {
    event.preventDefault()
    setProblem(null)
    if (!quoted && catalogue.length > 0 && !draft.plan_id) {
      setProblem(t('signup.choosePlan'))
      return
    }
    // Every field the form asks for, said at once and in the page's language.
    const required: [string, string][] = [
      ...(isCompany
        ? ([
            [draft.company_number, country.number_label],
            [draft.company, t('signup.companyName')],
          ] as [string, string][])
        : ([
            [draft.first_name, t('signup.firstName')],
            [draft.last_name, t('signup.lastName')],
          ] as [string, string][])),
      [draft.email, t('signup.email')],
      [draft.phone, t('signup.phone')],
      [draft.street, t('signup.address')],
      [draft.zip_code, t('signup.zip')],
      [draft.city, t('signup.city')],
      ...(quoted ? ([[draft.message, t('signup.need')]] as [string, string][]) : []),
    ]
    const missing = required.filter(([value]) => !value.trim()).map(([, label]) => label)
    if (missing.length) {
      setProblem(t('signup.missing', { fields: missing.join(', ') }))
      return
    }
    // The console's rule, said before the round trip.
    if (isCompany && inFrance && !checkSirenSiret(draft.company_number).ok) {
      setProblem(t('signup.badNumber'))
      return
    }
    setBusy(true)
    try {
      const { data } = await publicApi.accessRequest({
        ...draft,
        plan_id: quoted ? null : draft.plan_id || null,
      })
      setOutcome(data)
    } catch (error: any) {
      // The one refusal this server words itself before the console: an address the
      // e-mail validator rejects. Its raw sentence is the library's, in English.
      const detail = error?.response?.data?.detail
      const onEmail =
        error?.response?.status === 422 &&
        Array.isArray(detail) &&
        detail.some((d: any) => Array.isArray(d?.loc) && d.loc.includes('email'))
      setProblem(onEmail ? t('signup.badEmail') : errorMessage(error))
    } finally {
      setBusy(false)
    }
  }

  if (outcome) {
    const exists = outcome.status === 'account_exists'
    const warning = outcomeTone(outcome.status) === 'warning'
    const Icon = warning ? AlertTriangle : outcome.status === 'confirmation_sent' ? Mail : CheckCircle2
    return (
      <div ref={outcomeBox} className="space-y-3">
        <div
          className={`flex items-start gap-3 rounded-lg p-4 text-sm ${warning ? 'bg-amber-50 text-amber-900' : 'bg-emerald-50 text-emerald-900'}`}
        >
          <Icon size={18} className="mt-0.5 shrink-0" />
          <div className="space-y-1 min-w-0">
            <p className="font-medium">{t(outcomeTitleKey(outcome.status))}</p>
            <p className="break-words">{outcome.message}</p>
          </div>
        </div>
        {/* The way forward after an e-mail that did not leave or an answer that did not
            come: the same form, filled as it was, one tap away. */}
        {offersRetry(outcome.status) && (
          <Button type="button" onClick={() => setOutcome(null)}>
            {t('signup.retry')}
          </Button>
        )}
        {exists && (
          <div className="flex flex-wrap gap-3 text-sm">
            <a href={outcome.login_url || '/login'} className="text-brand-navy underline">
              {t('signup.signIn')}
            </a>
            {outcome.subscription_url && (
              <a href={outcome.subscription_url} className="text-brand-navy underline">
                {t('signup.subscription')}
              </a>
            )}
          </div>
        )}
        {onBack && (
          <button type="button" onClick={onBack} className="text-sm text-brand-navy underline">
            {t('signup.back')}
          </button>
        )}
      </div>
    )
  }

  const id = (name: string) => `${uid}-${name}`

  return (
    // ⚠️ `noValidate`: the browser's own bubble is a native dialog, in the browser's
    // language rather than the page's; the missing fields are said in the red box above.
    <form onSubmit={send} noValidate className="space-y-4">
      {problem && (
        <p ref={problemBox} className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{problem}</p>
      )}
      <Field label={t('signup.profile')} hint={t('signup.profileHint')}>
        <Select
          aria-label={t('signup.profile')}
          className={inputBaseClass}
          value={draft.profile}
          onChange={(profile) => set({ profile })}
          options={[
            { value: SINGLE_FUND, label: t('signup.profiles.single_fund') },
            { value: MANAGEMENT_COMPANY, label: t('signup.profiles.management_company') },
          ]}
        />
      </Field>
      {!quoted && (
        <Field
          label={t('signup.plan')}
          hint={plans !== null && catalogue.length === 0 ? t('signup.noPlan') : t('signup.planHint')}
        >
          <Select
            aria-label={t('signup.plan')}
            className={inputBaseClass}
            value={draft.plan_id}
            onChange={(plan_id) => set({ plan_id })}
            placeholder={plans === null ? t('common.loading') : t('signup.choosePlan')}
            options={catalogue.map((p) => ({
              value: p.id,
              label: [
                p.name,
                planPrice(p),
                p.investor_limit ? t('signup.upTo', { count: p.investor_limit }) : null,
              ]
                .filter(Boolean)
                .join(' · '),
            }))}
          />
        </Field>
      )}
      <Field label={t('signup.requesterKind')} hint={t('signup.requesterKindHint')}>
        <Select
          aria-label={t('signup.requesterKind')}
          className={inputBaseClass}
          value={draft.requester_kind}
          onChange={(requester_kind) => set({ requester_kind })}
          options={[
            { value: PERSON, label: t('signup.requesterKinds.personne') },
            { value: COMPANY, label: t('signup.requesterKinds.societe') },
          ]}
        />
      </Field>
      <Field label={t('signup.country')} hint={t('signup.countryHint')}>
        <Select
          aria-label={t('signup.country')}
          className={inputBaseClass}
          value={draft.country}
          onChange={(code) => set({ country: code, company_number: '' })}
          options={countries.map((c) => ({ value: c.code, label: c.name }))}
        />
      </Field>
      {isCompany ? (
        <>
          <Field
            label={country.number_label}
            htmlFor={id('number')}
            hint={inFrance ? t('signup.siretHint') : t('signup.numberHint')}
            required
          >
            {inFrance ? (
              <SiretInput
                id={id('number')}
                value={draft.company_number}
                onChange={(company_number) => set({ company_number })}
                onResolved={(found) =>
                  setDraft((d) => ({
                    ...d,
                    company: d.company || found.name || '',
                    street: d.street || found.street || '',
                    zip_code: d.zip_code || found.postcode || '',
                    city: d.city || found.city || '',
                  }))
                }
                className={inputBaseClass}
              />
            ) : (
              <input
                id={id('number')}
                required
                value={draft.company_number}
                onChange={(e) => set({ company_number: e.target.value })}
                className={inputBaseClass}
              />
            )}
          </Field>
          <Input
            label={t('signup.companyName')}
            hint={t('signup.companyNameHint')}
            required
            value={draft.company}
            onChange={(e) => set({ company: e.target.value })}
            autoComplete="organization"
          />
        </>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          <Input
            label={t('signup.firstName')}
            hint={t('signup.firstNameHint')}
            required
            value={draft.first_name}
            onChange={(e) => set({ first_name: e.target.value })}
            autoComplete="given-name"
          />
          <Input
            label={t('signup.lastName')}
            hint={t('signup.lastNameHint')}
            required
            value={draft.last_name}
            onChange={(e) => set({ last_name: e.target.value })}
            autoComplete="family-name"
          />
        </div>
      )}
      <Input
        label={t('signup.email')}
        hint={quoted ? t('signup.emailHintQuote') : t('signup.emailHint')}
        type="email"
        required
        value={draft.email}
        onChange={(e) => set({ email: e.target.value })}
        autoComplete="email"
      />
      <Input
        label={t('signup.phone')}
        hint={t('signup.phoneHint')}
        type="tel"
        required
        minLength={6}
        value={draft.phone}
        onChange={(e) => set({ phone: e.target.value })}
        autoComplete="tel"
      />
      <Field label={t('signup.address')} htmlFor={id('street')} hint={t('signup.addressHint')} required>
        <AddressAutocomplete
          id={id('street')}
          required
          country={draft.country}
          value={draft.street}
          onChange={(street) => set({ street })}
          onSelect={(parts) =>
            setDraft((d) => ({
              ...d,
              street: parts.street,
              zip_code: parts.postcode,
              city: parts.city,
              region: parts.region,
            }))
          }
          className={inputBaseClass}
        />
      </Field>
      <div className="grid gap-4 grid-cols-1 sm:grid-cols-3">
        <Input
          label={t('signup.zip')}
          hint={t('signup.zipHint')}
          required
          value={draft.zip_code}
          onChange={(e) => set({ zip_code: e.target.value })}
          autoComplete="postal-code"
        />
        <Input
          containerClassName="sm:col-span-2"
          label={t('signup.city')}
          hint={t('signup.cityHint')}
          required
          value={draft.city}
          onChange={(e) => set({ city: e.target.value })}
          autoComplete="address-level2"
        />
      </div>
      {quoted && (
        <Field label={t('signup.need')} htmlFor={id('need')} hint={t('signup.needHint')} required>
          <textarea
            id={id('need')}
            required
            rows={3}
            value={draft.message}
            onChange={(e) => set({ message: e.target.value })}
            className={inputBaseClass}
          />
        </Field>
      )}
      <p className="text-xs text-gray-500">{quoted ? t('signup.quoteNext') : t('signup.next')}</p>
      <div className="flex flex-wrap items-center justify-between gap-2">
        {onBack ? (
          <button type="button" onClick={onBack} className="text-sm text-brand-navy underline">
            {t('signup.back')}
          </button>
        ) : (
          <span />
        )}
        <Button type="submit" isLoading={busy}>
          {quoted ? t('signup.askQuote') : t('signup.create')}
        </Button>
      </div>
    </form>
  )
}
