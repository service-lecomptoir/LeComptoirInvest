import { describe, expect, it } from 'vitest'
import { loginFor, safeNext } from './nextPath'
import router from '../router.tsx?raw'
import login from '../pages/Login.tsx?raw'
import client from '../api/client.ts?raw'

describe('the return after sign-in', () => {
  it('honours a path of this site, query and hash included', () => {
    expect(safeNext('/billing')).toBe('/billing')
    expect(safeNext('/investors?tab=kyc#top')).toBe('/investors?tab=kyc#top')
  })

  it('never sends the reader to another host (open redirect)', () => {
    for (const hostile of [
      'https://evil.example/billing',
      'http://evil.example',
      '//evil.example/billing',
      '/\\evil.example',
      'javascript:alert(1)',
      'evil.example',
      '/\t/evil.example',
      '/\n/evil.example',
      '',
      null,
      undefined,
    ]) {
      expect(safeNext(hostile), String(hostile)).toBeNull()
    }
  })

  it('never loops back to the sign-in', () => {
    expect(safeNext('/login')).toBeNull()
    expect(safeNext('/login?next=%2Fbilling')).toBeNull()
  })

  it('builds the sign-in address that carries the way back', () => {
    expect(loginFor('/billing')).toBe('/login?next=%2Fbilling')
    expect(loginFor('/investors?tab=kyc')).toBe('/login?next=%2Finvestors%3Ftab%3Dkyc')
    expect(loginFor('/')).toBe('/login')
    expect(loginFor('//evil.example')).toBe('/login')
  })
})


describe('every door that sends to the sign-in carries the way back', () => {
  it('the signed-in guard, the expired session and the sign-in page all use it', () => {
    expect(router).toContain('<Navigate to={loginFor(')
    expect(client).toContain('window.location.href = loginFor(')
    // The sign-in reads `next` through the filter, never raw.
    expect(login).toContain("safeNext(params.get('next'))")
    expect(login).not.toMatch(/navigate\(params\.get/)
  })
})
