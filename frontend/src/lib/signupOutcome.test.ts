import { describe, expect, it } from 'vitest'

import fr from '@/i18n/locales/fr.json'
import { KNOWN_OUTCOMES, offersRetry, outcomeTitleKey, outcomeTone } from './signupOutcome'

describe('the screen after a sign-up', () => {
  it('shows in green only what went all the way', () => {
    expect(outcomeTone('confirmation_sent')).toBe('success')
    expect(outcomeTone('received')).toBe('success')
    expect(outcomeTone('confirmation_not_sent')).toBe('warning')
    expect(outcomeTone('not_answered')).toBe('warning')
    expect(outcomeTone('account_exists')).toBe('warning')
  })

  it('offers to try again after an e-mail that did not leave or an answer that did not come', () => {
    expect(offersRetry('confirmation_not_sent')).toBe(true)
    expect(offersRetry('not_answered')).toBe(true)
    expect(offersRetry('confirmation_sent')).toBe(false)
    expect(offersRetry('account_exists')).toBe(false)
  })

  it('never titles an e-mail that did not leave « Vérifiez votre boîte e-mail »', () => {
    const outcomes = fr.signup.outcomes as Record<string, string>
    const title = (status: string) => outcomes[outcomeTitleKey(status).split('.').pop()!]
    expect(title('confirmation_not_sent')).toBe('E-mail non envoyé')
    expect(title('not_answered')).not.toMatch(/boîte/)
    expect(title('something_new')).toBe(outcomes.received)
    for (const status of KNOWN_OUTCOMES) expect(outcomes[status], status).toBeTruthy()
  })
})
