import { useTranslation } from 'react-i18next'
import type { PublicPlan } from '@/api'
import { money } from './format'

/**
 * « 49,00 € par mois », or « Gratuit »: how a catalogue plan's price reads, on the pricing
 * page and in the sign-up's plan list alike. The price is the console's, in euros, excluding
 * tax; it is never written here.
 */
/**
 * Does this plan come with the free demo? Only a PRICED CATALOGUE plan does (as Le Comptoir
 * Immo, 7 Sept): a quotation has no price to try, a free plan nothing to pay after the demo.
 * No number of days is ever written next to it: none exists, the demo runs until the plan
 * is switched. One rule for the pricing page and the sign-up's plan cards.
 */
export function showsFreeDemo(plan: PublicPlan): boolean {
  return !plan.sur_devis && plan.monthly_price > 0
}

export function usePlanPrice() {
  const { t } = useTranslation()
  return (plan: PublicPlan) =>
    plan.monthly_price === 0
      ? t('pricing.free')
      : t('pricing.perMonth', { amount: money(plan.monthly_price, 'EUR') })
}
