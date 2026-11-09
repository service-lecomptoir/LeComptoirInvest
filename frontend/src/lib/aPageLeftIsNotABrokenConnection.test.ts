import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import clientSource from '../api/client.ts?raw'
import { NO_RESPONSE_GRACE_MS, markBack, markLeaving, sayUnlessLeaving } from './pageLeaving'

const SOURCES = import.meta.glob('../**/*.{ts,tsx}', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

/**
 * The owner, 9 Nov 2026: on the iPhone, « Connexion au serveur impossible » at every click on
 * « Ajouter un moyen de paiement » in Le Comptoir Immo, just before Stripe opened, and « on a
 * ça potentiellement dans toutes les applis ». A request cut short by leaving the page is a
 * network error with no response for iOS Safari, and the interceptor toasted it when a write was cut short.
 */
describe('a page left is not a broken connection', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    markBack()
  })
  afterEach(() => {
    vi.useRealTimers()
    markBack()
  })

  it('drops the error of a request cut short by leaving', () => {
    const say = vi.fn()
    sayUnlessLeaving(say)
    markLeaving()
    vi.advanceTimersByTime(NO_RESPONSE_GRACE_MS + 1)
    expect(say).not.toHaveBeenCalled()
  })

  it('still says a connection that is really down', () => {
    const say = vi.fn()
    sayUnlessLeaving(say)
    vi.advanceTimersByTime(NO_RESPONSE_GRACE_MS + 1)
    expect(say).toHaveBeenCalledTimes(1)
  })

  it('is what the interceptor does with a response-less error, and a restored page reloads', () => {
    expect(clientSource).toContain('sayUnlessLeaving(')
    expect(clientSource).toContain('watchPageLeaving(() => location.reload())')
  })

  it('sends the browser to another site through leaveFor only', () => {
    // A server-given address (Stripe's page, its portal, an invoice to pay) assigned by
    // hand would leave without telling the page, and the requests it cuts short would be
    // said. `tel:`, `sms:`, `mailto:` and our own paths stay on the page: they are not departures.
    const offenders = Object.entries(SOURCES)
      .filter(([path]) => !path.endsWith('/pageLeaving.ts') && !path.includes('.test.'))
      .flatMap(([path, source]) =>
        [...source.matchAll(/(?<![\w.])(?:window\.)?location\.(?:href\s*=(?!=)|assign\(|replace\()\s*([^;\n]*)/g)]
          .map(m => m[1].trim())
          .filter(target => !/^[`'"](?:\/|tel:|sms:|mailto:)/.test(target))
          // This product's own screens, named by a constant.
          .filter(target => !/^(?:loginFor\(|SUBSCRIPTION_ROUTE$)/.test(target))
          .map(target => `${path}: ${target}`),
      )
    expect(offenders).toEqual([])
  })
})
