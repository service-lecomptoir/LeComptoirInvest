import { describe, expect, it } from 'vitest'
import { readConsoleLink, withoutLink } from './consoleLink'
import login from '../pages/Login.tsx?raw'
import fr from '../i18n/locales/fr.json'
import en from '../i18n/locales/en.json'

/**
 * The console's sign-in link opens something (5 Nov 2026): a session, or the code step when
 * the holder's second factor is on. Until then the page ignored it.
 */
describe('the console sign-in link', () => {
  it('reads the session from the query', () => {
    expect(readConsoleLink('?token=abc', '')).toEqual({ session: 'abc', twoFactor: null })
  })

  it('reads the code step from the fragment, never from the query', () => {
    expect(readConsoleLink('', '#two_factor=xyz')).toEqual({ session: null, twoFactor: 'xyz' })
    expect(readConsoleLink('?two_factor=xyz', '')).toEqual({ session: null, twoFactor: null })
  })

  it('reads nothing on an ordinary visit', () => {
    expect(readConsoleLink('?next=%2Fprojects', '')).toEqual({ session: null, twoFactor: null })
  })

  it('takes the token out of the address bar and keeps the rest', () => {
    expect(withoutLink('?token=abc')).toBe('')
    expect(withoutLink('?token=abc&next=%2Fprojects')).toBe('?next=%2Fprojects')
  })

  it('is read by the sign-in page, which opens the session or the code step', () => {
    expect(login).toContain('readConsoleLink(')
    expect(login).toContain('adopt(link.session)')
    expect(login).toContain('link.twoFactor')
    expect(login).toContain("t('login.errors.linkInvalid')")
  })

  it('says a refused link in both languages', () => {
    for (const catalogue of [fr, en] as Array<Record<string, any>>) {
      expect(catalogue.login.errors.linkInvalid).toBeTruthy()
    }
  })
})
