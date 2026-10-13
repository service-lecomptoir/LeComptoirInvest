import { useTranslation } from 'react-i18next'
import { apiClient } from '@/api/client'

/**
 * The words and the server `PlanChangeOffer` uses in THIS product (`planOfferKit.tsx`
 * holds its window, fields, bubble and buttons): kept apart so the kit exports components only.
 */

/** The words under `planChange`, in the reader's language, and that language. */
export function usePlanWords(): { t: (key: string, vars?: Record<string, unknown>) => string; language: string } {
  const { t, i18n } = useTranslation()
  return { t: (key, vars) => String(t(`planChange.${key}`, vars ?? {})), language: i18n.language }
}

export const planHttp = {
  get: async <T,>(url: string): Promise<T> => (await apiClient.get<T>(url, { skipErrorToast: true })).data,
  post: async <T,>(url: string, body: unknown): Promise<T> =>
    (await apiClient.post<T>(url, body, { skipErrorToast: true })).data,
}

/** The current plan's mark, in the product's colour. */
export const PLAN_ACCENT = {
  card: 'border-brand-teal bg-brand-teal/5',
  badge: 'bg-brand-teal/10 text-brand-teal',
}
