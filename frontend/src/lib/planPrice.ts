import { useTranslation } from 'react-i18next'
import type { PublicPlan } from '@/api'
import { money } from './format'

/**
 * « 49,00 € par mois », or « Gratuit »: how a catalogue plan's price reads, on the pricing
 * page and in the sign-up's plan list alike. The price is the console's, in euros, excluding
 * tax; it is never written here.
 */
export function usePlanPrice() {
  const { t } = useTranslation()
  return (plan: PublicPlan) =>
    plan.monthly_price === 0
      ? t('pricing.free')
      : t('pricing.perMonth', { amount: money(plan.monthly_price, 'EUR') })
}
