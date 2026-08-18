import axios from 'axios'
import i18n from '@/i18n'
import { toast } from '@/store/toast'

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

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) config.headers.Authorization = `Bearer ${token}`
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

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const config = error?.config || {}
    const method = (config.method || 'get').toLowerCase()
    const isRead = method === 'get' || method === 'head'
    if (error?.response?.status === 401) {
      localStorage.removeItem(TOKEN_KEY)
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login'
      }
      return Promise.reject(error)
    }
    // A read's failure is the screen's problem; a write's failure is news the user is
    // owed, because they asked for something and it did not happen.
    if (!isRead && !config.skipErrorToast) toast.error(errorMessage(error))
    return Promise.reject(error)
  },
)
