import axios from 'axios'
import i18n from '@/i18n'
import { toast } from '@/store/toast'
import { sayUnlessLeaving, watchPageLeaving } from '@/lib/pageLeaving'
import { loginFor } from '@/lib/nextPath'
import { leaveSessionNotice } from '@/lib/sessionNotice'

declare module 'axios' {
  export interface AxiosRequestConfig {
    /** Lets a call handled locally switch the global error toast off. */
    skipErrorToast?: boolean
  }
}

const API_URL = import.meta.env.VITE_API_URL || ''

export const apiClient = axios.create({
  baseURL: `${API_URL}/api/v1`,
  headers: { 'Content-Type': 'application/json' },
})

export const TOKEN_KEY = 'lecomptoirinvest-token'

/** The pages open without an account: an expired session never redirects away from them. */
const PUBLIC_DOORS = ['/login', '/pricing', '/privacy']

/** The machine codes of a refusal under the firm's licence (`X-Error-Code`, 8 Nov 2026). */
const CLOSED_FIRM = ['agency_suspended', 'licence_ended']
/** The subscriber held to « Mon abonnement », suspended or ended (403, 9 Nov 2026). A 401
 *  `licence_ended` is the team's, signed out; a 403 is the subscriber's, sent to his page. */
const HELD_SUBSCRIBER = ['subscription_suspended', 'licence_ended']
/** The one screen a held subscriber is served. */
export const SUBSCRIPTION_ROUTE = '/billing'

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) config.headers.Authorization = `Bearer ${token}`
  // 🔴 THE SERVER REFUSES IN THE READER'S LANGUAGE, AND ONLY IF IT IS TOLD WHICH ONE.
  //
  // `errorMessage` below shows `detail` verbatim, so every refusal that matters is written
  // on the server. The browser sends its own `Accept-Language` from the operating system,
  // which is precisely NOT the choice the user made in the language switcher: leaving it
  // alone would translate the screen and leave the sentences behind.
  config.headers['Accept-Language'] = i18n.language || 'fr'
  return config
})

/**
 * 🔴 THE SERVER'S SENTENCE IS SHOWN, NEVER A BARE « Erreur ».
 *
 * This API refuses things for reasons that are the whole point of the product — the
 * lenders are not covered, this loan's schedule is not recorded, that transfer is an
 * incoming one. Swallowing `detail` and printing a generic failure would hide exactly
 * the sentence the user needs, and they would retry the same thing.
 */
export function errorMessage(error: any): string {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail) && detail.length) {
    const first = detail[0]
    if (typeof first?.msg === 'string') return first.msg
  }
  if (error?.response?.status === 401) return i18n.t('errors.expired')
  if (error?.message === 'Network Error') return i18n.t('errors.network')
  return error?.message || i18n.t('errors.generic')
}

// A page restored from the back-forward cache reloads, instead of showing what it held
// when it left (`lib/pageLeaving.ts`, the owner, 9 Nov 2026).
if (typeof window !== 'undefined') watchPageLeaving(() => location.reload())

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const config = error?.config || {}
    const method = (config.method || 'get').toLowerCase()
    const isRead = method === 'get' || method === 'head'
    const code = error?.response?.headers?.['x-error-code']
    if (error?.response?.status === 401) {
      // 🔴 A CLOSED FIRM SAYS WHY ON THE SIGN-IN PAGE (8 Nov 2026), never an empty form.
      if (CLOSED_FIRM.includes(code)) leaveSessionNotice(errorMessage(error))
      localStorage.removeItem(TOKEN_KEY)
      // ⚠️ NOT FROM A PUBLIC DOOR: a visitor on the pricing page holding a stale token
      // would be thrown to the sign-in while reading the prices.
      if (!PUBLIC_DOORS.some((door) => window.location.pathname.startsWith(door))) {
        const { pathname, search, hash } = window.location
        window.location.href = loginFor(`${pathname}${search}${hash}`)
      }
      return Promise.reject(error)
    }
    // 🔴 A SUSPENDED SUBSCRIBER IS SENT TO « MON ABONNEMENT », WITHOUT A TOAST: the
    // server serves them nothing else until they settle (8 Nov 2026), nor the subscriber
    // of an ended licence until they subscribe again (9 Nov 2026).
    if (error?.response?.status === 403 && HELD_SUBSCRIBER.includes(code)) {
      if (!window.location.pathname.startsWith(SUBSCRIPTION_ROUTE)) {
        window.location.href = SUBSCRIPTION_ROUTE
      }
      return Promise.reject(error)
    }
    // 🔴 402 IS A QUESTION, NOT A FAILURE, AND IT IS ANSWERED BY THE SCREEN.
    //
    // The server sends it when an action exceeds the plan's allowance and the plan ALLOWS
    // the overage: the sentence carries the count and the monthly price, and the screen
    // must show it in a dialog with a « confirm » button, not flash it in a red toast that
    // disappears. Toasting it here would tell the user something went wrong when in fact
    // nothing has: they are being asked whether to spend more.
    const isQuestion = error?.response?.status === 402
    // A read's failure is the screen's problem; a write's failure is news the user is
    // owed, because they asked for something and it did not happen.
    const fail = () => {
      if (!isRead && !isQuestion && !config.skipErrorToast) toast.error(errorMessage(error))
      return error
    }
    // 🔴 A response-less error may be a request cut short by leaving the page (a payment
    // button sends the browser to Stripe): the toast AND the rejection wait a beat, and are
    // held while the page is being left (`lib/pageLeaving.ts`, the owner, 9 Nov 2026). The
    // rejection too: a screen that shows its own load error said it on the iPhone just
    // before Stripe opened, once the toast was held (« Mon abonnement » in Le Comptoir Immo).
    if (!error?.response) return new Promise((_, reject) => sayUnlessLeaving(() => reject(fail())))
    return Promise.reject(fail())
  },
)
