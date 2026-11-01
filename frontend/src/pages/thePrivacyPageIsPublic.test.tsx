/**
 * The privacy notice and legal information (the owner, 1 Nov 2026): one public page that
 * draws Alice's text (`kind = "prv"`) and the list of sub-processors under it, reached from
 * the sign-in page, the public pages and the account menu.
 */
import type { ReactElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { StaticRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import i18n from '@/i18n'
import en from '@/i18n/locales/en.json'
import fr from '@/i18n/locales/fr.json'
import CLIENT from '../api/client.ts?raw'
import TERMS_API from '../api/terms.ts?raw'
import MENU from '../components/layout/ProfileMenu.tsx?raw'
import TERMS from '../lib/terms.ts?raw'
import ROUTER from '../router.tsx?raw'

import LANDING from './Landing.tsx?raw'
import LOGIN from './Login.tsx?raw'
import PRICING from './Pricing.tsx?raw'
import Privacy from './Privacy'
import PAGE from './Privacy.tsx?raw'

const render = (element: ReactElement) => renderToStaticMarkup(element).split('&#x27;').join("'")

describe('the privacy page', () => {
  it('is served without an account, before the guard and the terms gate', () => {
    const route = ROUTER.indexOf("{ path: '/privacy', element: <Privacy /> }")
    expect(route).toBeGreaterThan(-1)
    expect(route).toBeLessThan(ROUTER.indexOf('element: <RequireAuth />'))
    // A stale session never throws a visitor off it to the sign-in.
    expect(CLIENT).toMatch(/PUBLIC_DOORS = \[[^\]]*'\/privacy'/)
  })

  it('reads Alice text through the public relay, and the sub-processors under it', () => {
    expect(TERMS).toContain(".forSignup('prv', language)")
    expect(TERMS_API).toContain('forSignup: (kind: PublicTermsKind, language: string)')
    expect(PAGE).toContain('<TermsBody text={notice.text} scroll={false} />')
    expect(PAGE).toContain('<Subprocessors />')
  })

  it('says a text not published yet without a red block, and a silent Alice in one sentence', () => {
    expect(PAGE).toContain('<Notice tone="info" title={t(\'privacy.notPublishedTitle\')}>')
    expect(PAGE).toContain('<Notice tone="warn" title={t(\'privacy.unavailableTitle\')}>')
    expect(PAGE).not.toContain('tone="bad"')
  })

  it('draws its title and waits for the text', async () => {
    await i18n.changeLanguage('fr')
    const html = render(
      <StaticRouter location="/privacy">
        <Privacy />
      </StaticRouter>,
    )
    expect(html).toContain(fr.privacy.title)
    expect(html).toContain(fr.privacy.loading)
  })

  it('is reached from the sign-in page, the public pages and the account menu', () => {
    expect(LOGIN).toContain('<Link to="/privacy"')
    expect(LANDING).toContain('<Link to="/privacy"')
    expect(PRICING).toContain('<Link to="/privacy"')
    expect(MENU).toContain("navigate('/privacy')")
  })

  it('is named in both languages', () => {
    expect(fr.privacy.title).toBe('Confidentialité et mentions légales')
    for (const catalogue of [fr, en]) {
      for (const key of ['title', 'back', 'loading', 'notPublishedTitle', 'notPublished', 'unavailableTitle', 'unavailable'] as const) {
        expect(catalogue.privacy[key]).toBeTruthy()
      }
    }
  })
})
