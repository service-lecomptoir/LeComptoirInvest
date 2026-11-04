import { describe, expect, it } from 'vitest'

import en from '@/i18n/locales/en.json'
import fr from '@/i18n/locales/fr.json'
import GUIDE_PAGE from '@/pages/Guide.tsx?raw'
import LANDING from '@/pages/Landing.tsx?raw'
import LOGIN from '@/pages/Login.tsx?raw'
import PRICING from '@/pages/Pricing.tsx?raw'

import MENU from './ProfileMenu.tsx?raw'
import SHELL from './Shell.tsx?raw'

/**
 * « Confidentialité et mentions légales » (the owner, 2 Nov 2026: « sa place n'est pas là »,
 * about the account menu, where the link had been put on 1 Nov). It is a small link at the
 * very foot of the side menu, and it stays on the sign-in page, the pricing page and the
 * public home. This product has one page for both (`/privacy`, Alice's text `prv`), hence
 * one link.
 */
describe('the privacy and legal notice link', () => {
  const foot = SHELL.slice(SHELL.indexOf('function RailFoot'), SHELL.indexOf('const OFF_MENU_TITLES'))

  it('sits at the foot of the side menu, small, and closes the drawer', () => {
    expect(foot).toContain('<Link to="/privacy" onClick={onNavigate}')
    expect(foot).toContain("t('privacy.title')")
    expect(foot).toContain('text-[11px]')
    expect(foot).toContain('hover:underline')
    expect(foot).not.toMatch(/size=\{/)
    // After the navigation, in the side menu the desktop and the phone drawer share.
    const aside = SHELL.slice(SHELL.indexOf('const aside = ('))
    expect(aside.indexOf('<RailFoot onNavigate={() => setOpen(false)} />')).toBeGreaterThan(
      aside.indexOf('<NavList onNavigate={() => setOpen(false)} />'),
    )
  })

  it('has left the account menu, with its icon', () => {
    expect(MENU).not.toContain('/privacy')
    expect(MENU).not.toContain('privacy.title')
    expect(MENU).not.toContain('ShieldCheck')
  })

  it('stays on the sign-in page, the pricing page and the public home', () => {
    for (const page of [LOGIN, PRICING, LANDING]) expect(page).toContain('<Link to="/privacy"')
  })

  it('is told where it is by the guide', () => {
    expect(GUIDE_PAGE).toContain("'guide.everywhere.privacy'")
    expect(fr.guide.everywhere.privacy).toContain('tout en bas du menu de gauche')
    expect(en.guide.everywhere.privacy).toContain('very foot of the left menu')
  })
})
