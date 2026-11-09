import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  NO_RESPONSE_GRACE_MS,
  STILL_HERE_AFTER_MS,
  leaveFor,
  markBack,
  sayUnlessLeaving,
  watchPageLeaving,
} from './pageLeaving'

/**
 * `beforeunload` is not a departure: a « Leave site? » prompt the user cancels, or a
 * navigation that fails, keeps the page. Raising « page left » there left it raised for
 * good, and every later response-less error was silenced (or held for ever).
 */
describe('a departure that does not happen', () => {
  let page: EventTarget & { location: { href: string } }

  beforeEach(() => {
    vi.useFakeTimers()
    page = Object.assign(new EventTarget(), { location: { href: '' } })
    vi.stubGlobal('window', page)
    markBack()
    watchPageLeaving(() => undefined)
  })
  afterEach(() => {
    markBack()
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('says the errors after a « Leave site? » prompt the user cancelled', () => {
    page.dispatchEvent(new Event('beforeunload'))
    const say = vi.fn()
    sayUnlessLeaving(say)
    vi.advanceTimersByTime(NO_RESPONSE_GRACE_MS + 1)
    expect(say).toHaveBeenCalledTimes(1)
  })

  it('says, once the page is still here, the errors held while it was leaving for another site', () => {
    leaveFor('https://checkout.stripe.com/pay')
    expect(page.location.href).toBe('https://checkout.stripe.com/pay')
    const held = vi.fn()
    sayUnlessLeaving(held)
    vi.advanceTimersByTime(NO_RESPONSE_GRACE_MS + 1)
    expect(held).not.toHaveBeenCalled()
    vi.advanceTimersByTime(STILL_HERE_AFTER_MS)
    expect(held).toHaveBeenCalledTimes(1)
    const later = vi.fn()
    sayUnlessLeaving(later)
    vi.advanceTimersByTime(NO_RESPONSE_GRACE_MS + 1)
    expect(later).toHaveBeenCalledTimes(1)
  })

  it('stays silent when the page really leaves', () => {
    leaveFor('https://checkout.stripe.com/pay')
    page.dispatchEvent(new Event('pagehide'))
    const say = vi.fn()
    sayUnlessLeaving(say)
    vi.advanceTimersByTime(NO_RESPONSE_GRACE_MS + STILL_HERE_AFTER_MS)
    expect(say).not.toHaveBeenCalled()
  })

  it('forgets what it held when the page comes back from the cache, and reloads instead', () => {
    const restored = vi.fn()
    watchPageLeaving(restored)
    page.dispatchEvent(new Event('pagehide'))
    const say = vi.fn()
    sayUnlessLeaving(say)
    vi.advanceTimersByTime(NO_RESPONSE_GRACE_MS + 1)
    page.dispatchEvent(Object.assign(new Event('pageshow'), { persisted: true }))
    vi.advanceTimersByTime(STILL_HERE_AFTER_MS)
    expect(restored).toHaveBeenCalledTimes(1)
    expect(say).not.toHaveBeenCalled()
  })
})
