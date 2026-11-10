import { AxiosError, type InternalAxiosRequestConfig } from 'axios'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { apiClient } from '../api/client'
import { NO_RESPONSE_GRACE_MS, markBack, markLeaving, markStillHere } from './pageLeaving'

/**
 * The owner, 9 Nov 2026, once the toast of a request cut short by leaving was held in
 * Le Comptoir Immo: « toujours l'erreur du serveur, y'en a un seul pas 2 ». « Mon
 * abonnement » shows its own load error from the rejection, and replaced its whole content
 * with « Connexion au serveur impossible » just before Stripe opened. The client holds the
 * rejection too, in every product.
 */
describe('a screen hears nothing of a request cut short by leaving', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    // No browser here: the client reads its token from a hand-made `localStorage`.
    vi.stubGlobal('localStorage', { getItem: () => null, setItem: () => undefined, removeItem: () => undefined })
    markBack()
  })
  afterEach(() => {
    markBack()
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  // A load cut short: no response, as iOS Safari reports a request aborted by a departure.
  const load = () =>
    apiClient.get('/subscription', {
      adapter: (config: InternalAxiosRequestConfig) =>
        Promise.reject(new AxiosError('Network Error', 'ERR_NETWORK', config)),
      skipErrorToast: true,
    } as never)

  it('holds the rejection while the page is being left', async () => {
    const onError = vi.fn()
    load().catch(onError)
    markLeaving()
    await vi.advanceTimersByTimeAsync(NO_RESPONSE_GRACE_MS + 1)
    expect(onError).not.toHaveBeenCalled()
  })

  it('still hands a connection really down to the screen', async () => {
    const onError = vi.fn()
    load().catch(onError)
    await vi.advanceTimersByTimeAsync(NO_RESPONSE_GRACE_MS + 1)
    expect(onError).toHaveBeenCalledTimes(1)
  })

  it('hands the error back when the departure did not happen', async () => {
    const onError = vi.fn()
    load().catch(onError)
    markLeaving()
    await vi.advanceTimersByTimeAsync(NO_RESPONSE_GRACE_MS + 1)
    markStillHere()
    await vi.advanceTimersByTimeAsync(0)
    expect(onError).toHaveBeenCalledTimes(1)
  })
})
