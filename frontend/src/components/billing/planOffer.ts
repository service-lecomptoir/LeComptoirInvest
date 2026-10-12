/**
 * Alice's plan offer as this product's server relays it (`services/plan_change.py` in
 * Alice): the shapes, the routes, and the two readings the page makes of it.
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
  return typeof detail === 'string' && detail.trim() ? detail : fallback
}

/** Why the current plan is not left by a click, as a key, or null when it is. */
export function handedOutKey(offer: Offer): string | null {
  if (!offer.self_service) return `planChange.handedOut.${offer.current_kind === 'none' ? 'technical' : offer.current_kind}`
  return offer.mode === 'request' && offer.plans.some(plan => !plan.is_current) ? 'planChange.noOnlinePayment' : null
}
