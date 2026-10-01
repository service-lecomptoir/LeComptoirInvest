import { describe, expect, it } from 'vitest'
import login from './Login.tsx?raw'
import fr from '../i18n/locales/fr.json'
import en from '../i18n/locales/en.json'

/**
 * The sign-in page, laid out as Le Comptoir Immo's, keeps every door it had.
 *
 * 🔴 A REDESIGN IS WHERE A DOOR GOES MISSING: the forgotten password (there was none until
 * 30 Sept 2026, and the only way back was writing to support), the language picker (the
 * reader who cannot read the form is the one who needs it), the way to the public page, and
 * the house rule of no word in capitals.
 */
describe('the sign-in page', () => {
  it('keeps the forgotten password, opening the existing flow', () => {
    expect(login).toContain("t('login.forgot')")
    expect(login).toContain('setForgetting(true)')
    expect(login).toContain('authApi.forgotPassword(')
  })

  it('offers the language picker', () => {
    expect(login).toContain('<LanguageSwitcher')
  })

  it('writes no word in capitals', () => {
    expect(login).not.toMatch(/\buppercase\b/)
  })

  it('leads to the public page and to the sign-up', () => {
    expect(login).toContain('<Link to="/"')
    expect(login).toContain('setSigningUp(true)')
  })

  it('never says « wrong password » for a server that is down or unreachable', () => {
    expect(login).toContain("if (!err?.response) return t('login.errors.unreachable')")
    expect(login).toContain("return t('login.errors.unavailable')")
    for (const catalogue of [fr, en] as Array<Record<string, any>>) {
      for (const key of ['badCredentials', 'invalidEmail', 'unavailable', 'serverError', 'unreachable']) {
        expect(catalogue.login.errors[key], key).toBeTruthy()
      }
    }
  })

  it('says the connection is secure only when the page came over HTTPS', () => {
    expect(login).toContain("window.location.protocol === 'https:'")
    expect(login).toContain('{secured && (')
  })
})
