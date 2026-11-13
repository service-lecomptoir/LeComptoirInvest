/**
 * The ended subscription's banner, a write refused during the thirty days to export, and
 * the banners' days written JJ/MM/AAAA (the owner, 13 Nov 2026). One rule per test.
 */

import { afterEach, describe, expect, it } from 'vitest'
import i18n from '@/i18n'
import { bannerDay, endedWords } from './subscriptionBanner'
import { useToastStore } from '@/store/toast'
import client from '@/api/client.ts?raw'
import banner from '@/components/layout/SubscriptionBanner.tsx?raw'
import bannerWords from '@/lib/subscriptionBanner.ts?raw'
import termsBanner from '@/components/terms/UpcomingTermsBanner.tsx?raw'
import termsReader from '@/components/terms/TermsReader.tsx?raw'
import toasts from '@/components/common/Toasts.tsx?raw'

const t = (key: string, vars?: Record<string, string>) => i18n.t(key, vars) as string

afterEach(async () => {
  await i18n.changeLanguage('fr')
  useToastStore.setState({ toasts: [] })
})

describe('the banner of an ended subscription', () => {
  it('says the day the data are erased', async () => {
    await i18n.changeLanguage('fr')
    const words = endedWords(
      { exports_open: true, export_until: '2026-12-19T22:59:59+00:00', erase_on: '2026-12-20' },
      t,
    )
    expect(words).toContain('Vos données seront effacées le 20/12/2026.')
  })

  it('says nothing of an erasure no one scheduled', async () => {
    await i18n.changeLanguage('fr')
    const words = endedWords({ exports_open: true, export_until: '2026-12-19T22:59:59+00:00', erase_on: null }, t)
    expect(words).not.toContain('effacées')
  })

  it('says it in the reader’s language', async () => {
    await i18n.changeLanguage('en')
    expect(endedWords({ exports_open: false, export_until: null, erase_on: '2027-03-03' }, t)).toContain(
      'Your data will be erased on 03/03/2027.',
    )
  })
})

describe('a banner writes its day JJ/MM/AAAA', () => {
  it('in every language', async () => {
    for (const lang of ['fr', 'en']) {
      await i18n.changeLanguage(lang)
      expect(bannerDay('2026-12-01')).toBe('01/12/2026')
    }
  })

  it('through the product’s one formatter, with a pattern', () => {
    expect(bannerWords).toContain("day(value, 'dd/MM/yyyy')")
  })

  it('the thirty days, the erasure and the new terms alike', () => {
    expect(bannerWords).toMatch(/bannerDay\(info\.export_until\)/)
    expect(bannerWords).toMatch(/bannerDay\(info\.erase_on\)/)
    expect(banner).toContain('endedWords(info, t)')
    expect(termsBanner).toMatch(/bannerDay\(upcoming\.effective_from\)/)
    expect(termsReader).toMatch(/upcoming\.hint', \{ date: bannerDay\(/)
  })
})

describe('a write refused during the thirty days to export', () => {
  it('is said where it was tried, with « Mon abonnement » a click away, never a redirect', () => {
    const block = client.slice(
      client.indexOf('code === SUBSCRIPTION_READ_ONLY'),
      client.indexOf('HELD_SUBSCRIBER.includes(code)) {'),
    )
    expect(block).toMatch(/toast\.error\(errorMessage\(error\), \{ to: SUBSCRIPTION_ROUTE/)
    expect(block).not.toMatch(/location/)
  })

  it('comes before the confinement, which stays as it was after the thirty days', () => {
    expect(client.indexOf('code === SUBSCRIPTION_READ_ONLY')).toBeGreaterThan(0)
    expect(client.indexOf('code === SUBSCRIPTION_READ_ONLY')).toBeLessThan(
      client.indexOf('HELD_SUBSCRIBER.includes(code)) {'),
    )
    expect(client).toMatch(
      /HELD_SUBSCRIBER\.includes\(code\)\) \{\s*if \(!window\.location\.pathname\.startsWith\(SUBSCRIPTION_ROUTE\)\) \{\s*window\.location\.href = SUBSCRIPTION_ROUTE/,
    )
  })

  it('the message carries its link, and the same sentence is not drawn twice', () => {
    const { push } = useToastStore.getState()
    push('error', 'Abonnement terminé', { to: '/billing', label: 'Mon abonnement' })
    push('error', 'Abonnement terminé')
    const shown = useToastStore.getState().toasts
    expect(shown).toHaveLength(1)
    expect(shown[0].link).toEqual({ to: '/billing', label: 'Mon abonnement' })
  })

  it('the link is drawn and opens the screen through the router', () => {
    expect(toasts).toContain('{t.link.label}')
    expect(toasts).toContain('m.router.navigate(to)')
  })
})
