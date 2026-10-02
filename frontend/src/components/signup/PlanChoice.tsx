import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import { Award, Check, Crown, Gem, Medal } from 'lucide-react'
import type { PublicPlan } from '@/api'
import { usePlanPrice } from '@/lib/planPrice'

/**
 * The catalogue plans of the sign-up, as CARDS to choose from, the way Le Comptoir Immo's
 * « Créer mon compte » shows them (the manager, 1 Oct 2026): each card says the plan's
 * avatar and name, its price, its number of investors and, under a priced catalogue plan
 * only, « Démo gratuite incluse » in green.
 *
 * 🔴 A DROPDOWN HID THE DEMO: the list said « Essentiel · 29,00 € par mois · jusqu'à 5
 * investisseurs » and the demo appeared in the help only once a plan was picked. A card
 * says it before the choice.
 *
 * ⚠️ A RADIO GROUP, NOT BUTTONS: each card is a native radio (hidden, its card drawn around
 * it) inside a fieldset whose legend is the field's name, so the arrow keys move between
 * plans, the focus is drawn on the card, and a screen reader reads « Formule », the card's
 * text and whether it is selected.
 */
export function PlanChoice({
  plans,
  value,
  onChange,
  hint,
  error,
}: {
  /** `null` while the catalogue is on its way. */
  plans: PublicPlan[] | null
  value: string
  onChange: (planId: string) => void
  /** The help under the field (house rule: a hint under every field). */
  hint: string
  /** What the form's check found wrong: shown in red in place of the help. */
  error?: string
}) {
  const { t } = useTranslation()
  const planPrice = usePlanPrice()
  const name = useId()
  const hintId = `${name}-hint`
  return (
    <fieldset aria-describedby={hintId} aria-invalid={error ? true : undefined}>
      <legend className="mb-1 block text-sm font-medium text-gray-700">{t('signup.plan')}</legend>
      {plans === null ? (
        <p className="text-sm text-gray-500">{t('common.loading')}</p>
      ) : (
        <div className="space-y-2">
          {plans.map((plan) => {
            const selected = plan.id === value
            return (
              <label key={plan.id} className="block cursor-pointer">
                <input
                  type="radio"
                  name={name}
                  value={plan.id}
                  checked={selected}
                  onChange={() => onChange(plan.id)}
                  className="peer sr-only"
                />
                <span
                  className={`block rounded-xl border p-3 transition-all hover:border-gray-300 peer-checked:border-brand-navy peer-checked:bg-brand-navy/5 peer-checked:ring-2 peer-checked:ring-brand-navy/10 peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-brand-navy ${error ? 'border-red-500' : 'border-gray-200'}`}
                >
                  <span className="flex items-center justify-between gap-2">
                    <span className="flex min-w-0 items-center gap-1.5 text-sm font-semibold text-gray-900">
                      {selected && <Check size={14} className="shrink-0 text-brand-navy" aria-hidden="true" />}
                      <PlanTierBadge name={plan.name} size={20} />
                      <span className="truncate">{plan.name}</span>
                    </span>
                    <span className="whitespace-nowrap text-sm font-bold text-brand-navy">{planPrice(plan)}</span>
                  </span>
                  {plan.description && <span className="mt-1 block text-xs text-gray-500">{plan.description}</span>}
                  <span className="mt-1 block text-xs text-gray-500">
                    {plan.investor_limit ? t('pricing.upTo', { count: plan.investor_limit }) : t('pricing.unlimited')}
                  </span>
                  {/* The demo comes with a priced catalogue plan only, never a number of
                      days: none exists, the demo runs until the plan is switched. */}
                  {plan.free_demo && (
                    <span className="mt-0.5 block text-xs font-medium text-green-700">{t('pricing.freeDemo')}</span>
                  )}
                </span>
              </label>
            )
          })}
        </div>
      )}
      <p id={hintId} className={`mt-1 text-xs ${error ? 'text-red-600' : 'text-gray-500'}`}>{error ?? hint}</p>
    </fieldset>
  )
}

/** The metal tiers Le Comptoir Immo draws as a medal; any other plan gets its initials. */
const TIERS: { keys: string[]; color: string; icon: typeof Medal; iconColor?: string }[] = [
  { keys: ['signature'], color: '#0B0B0F', icon: Crown, iconColor: '#D4AF37' },
  { keys: ['bronze'], color: '#CD7F32', icon: Medal },
  { keys: ['argent', 'silver'], color: '#9CA3AF', icon: Medal },
  { keys: ['or', 'gold'], color: '#D4AF37', icon: Medal },
  { keys: ['platine', 'platinum'], color: '#7C8B9A', icon: Award },
  { keys: ['diamant', 'diamond'], color: '#22D3EE', icon: Gem },
]

const PALETTE = ['#0D2F5C', '#0E9F8E', '#4F46E5', '#7C3AED', '#DB2777', '#2563EB', '#059669', '#D97706', '#DC2626', '#0891B2']

/**
 * The plan's round avatar, Le Comptoir Immo's: a medal for a metal tier, otherwise the
 * initials in a colour drawn from the name, stable from one screen to the next. Decorative:
 * the name is written beside it, so a screen reader skips it.
 */
export function PlanTierBadge({ name, size }: { name: string; size: number }) {
  const lower = name.toLowerCase()
  const tier = TIERS.find((tierRow) => tierRow.keys.some((k) => new RegExp(`\\b${k}\\b`).test(lower)))
  const base = 'inline-flex shrink-0 items-center justify-center rounded-full shadow-sm ring-1 ring-black/10'
  if (tier) {
    const Icon = tier.icon
    return (
      <span aria-hidden="true" className={base} style={{ width: size, height: size, background: tier.color }}>
        <Icon size={Math.round(size * 0.58)} style={{ color: tier.iconColor ?? '#ffffff' }} strokeWidth={2.2} />
      </span>
    )
  }
  let hash = 0
  for (const char of lower) hash = (hash * 31 + char.charCodeAt(0)) | 0
  const words = name.trim().split(/\s+/).filter(Boolean)
  // Two letters of a monogram, not a word: they are drawn as capitals, as on Immo's badge.
  const initials = (words.length > 1 ? words[0][0] + words[words.length - 1][0] : (words[0] ?? '').slice(0, 2)).toUpperCase()
  return (
    <span aria-hidden="true" className={base} style={{ width: size, height: size, background: PALETTE[Math.abs(hash) % PALETTE.length] }}>
      <span className="font-bold leading-none text-white" style={{ fontSize: Math.round(size * 0.42) }}>
        {initials}
      </span>
    </span>
  )
}
