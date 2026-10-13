/**
 * Alice's plan offer as this product's server relays it (`services/plan_change.py` in
 * Alice): the shapes, the routes, and the readings the « Mon abonnement » page makes of it.
 *
 * 🔴 THE SAME FILE IN EVERY PRODUCT. The owner, 12 Oct 2026, who did not see the plan change
 * aligned: « je ne le vois toujours pas ». Nothing here prices or decides: it only
 * says which of the three faces of the page this offer calls for, in which order the cards
 * come, and which colour the usage takes. A copy that differs is the next page that does.
 */

export interface OfferPlan {
  id: string
  name: string
  description: string | null
  currency: string
  monthly_price: number
  price_ht: number
  vat_rate: number | null
  price_ttc: number | null
  managed_limit: number | null
  overage_allowed: boolean
  overage_price: number | null
  overage_count: number
  overage_monthly: number
  is_current: boolean
  action: 'change' | 'subscribe' | 'request' | 'current' | 'refused'
  refusal: { code: string; count: number; limit: number; message: string } | null
}

export interface Offer {
  managed_count: number
  current_kind: 'none' | 'catalogue' | 'bespoke' | 'beta' | 'quote' | 'technical'
  self_service: boolean
  current: OfferPlan | null
  mode: 'change' | 'subscribe' | 'request'
  plans: OfferPlan[]
  can_change: boolean
  /** The next payment (a day), or null: none announced (free, demo, ending). */
  next_due_date?: string | null
  /** The day the subscription ends, when an end is set. */
  ends_on?: string | null
}

export interface Preview {
  plan?: OfferPlan
  action?: OfferPlan['action']
  refusal?: OfferPlan['refusal']
  next_billing_date?: string | null
  proration_amount?: number
}

/** The terms of sale ticked beside the plans, as each product's page holds them. */
export type SaleTerms = { cgv?: string | null; language?: string } | false | null | undefined

/** This product's own routes, which relay Alice. */
export interface OfferRoutes {
  offer: string
  preview: string
  change: string
  checkout: string
  request: string
}

export const BILLING_ROUTES: OfferRoutes = {
  offer: '/billing/offer',
  preview: '/billing/change-plan-preview',
  change: '/billing/change-plan',
  checkout: '/billing/checkout',
  request: '/billing/change-request',
}

/** The server's own sentence, or the generic one. */
export function sentenceOf(error: unknown, fallback: string): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  const message = (error as { message?: unknown })?.message
  return error instanceof Error && typeof message === 'string' && message.trim() && !(error as { isAxiosError?: boolean }).isAxiosError
    ? message
    : fallback
}

/**
 * The face of the page:
 * - `standard`: a catalogue plan (or none) and other plans to take: the cards, « Choisir »,
 *   then « Demander une offre sur mesure »;
 * - `frozen`: a bespoke, beta-tester, « sur devis » or technical plan: ONE button,
 *   « Demander un changement », the catalogue plans compared in its window;
 * - `empty`: nothing else is published: the same single button, and a sentence that says so.
 */
export type OfferView = 'standard' | 'frozen' | 'empty'

export function offerView(offer: Offer): OfferView {
  if (!offer.self_service) return 'frozen'
  return offer.plans.some(plan => !plan.is_current) ? 'standard' : 'empty'
}

/** Why the current plan is not left by a click, as a key under `planChange`. */
export function handedOutKey(offer: Offer): string {
  return `handedOut.${offer.current_kind === 'none' || offer.current_kind === 'catalogue' ? 'technical' : offer.current_kind}`
}

/**
 * The cards, by increasing price, the current plan at its place (the owner, 12 Oct 2026:
 * « Argent, Bronze, Or » read as a ranking; Bronze, Argent, Or is one). Same price: the
 * smaller cap first, the unlimited last.
 */
export function cardsOf(offer: Offer): OfferPlan[] {
  const hasCurrent = offer.plans.some(plan => plan.is_current)
  const list = hasCurrent || !offer.current || !offer.self_service ? offer.plans : [...offer.plans, offer.current]
  return [...list].sort(
    (a, b) =>
      a.price_ht - b.price_ht ||
      (a.managed_limit ?? Number.POSITIVE_INFINITY) - (b.managed_limit ?? Number.POSITIVE_INFINITY),
  )
}

/** The plans a request may name: the catalogue plans other than the current one. */
export function requestablePlans(offer: Offer): OfferPlan[] {
  return cardsOf(offer).filter(plan => !plan.is_current)
}

/**
 * The colour of the usage (the owner, 12 Oct 2026: « 2 / 2 » drawn full and red read as an
 * overrun). No ceiling: no bar at all. At the ceiling: orange. Red only beyond it.
 */
export type UsageTone = 'none' | 'ok' | 'full' | 'over'

export function usageTone(count: number, limit: number | null): UsageTone {
  if (limit === null) return 'none'
  if (count > limit) return 'over'
  return count === limit ? 'full' : 'ok'
}

export function usagePercent(count: number, limit: number | null): number {
  if (limit === null) return 0
  return Math.min(100, Math.round((count / Math.max(1, limit)) * 100))
}

export const USAGE_BAR: Record<Exclude<UsageTone, 'none'>, string> = {
  ok: 'bg-emerald-500',
  full: 'bg-amber-500',
  over: 'bg-red-500',
}
