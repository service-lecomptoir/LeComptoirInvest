import { describe, expect, it } from 'vitest'
import router from '../router.tsx?raw'
import pricing from './Pricing.tsx?raw'
import login from './Login.tsx?raw'
import client from '../api/client.ts?raw'
import signup from '../components/signup/SignupForm.tsx?raw'

/**
 * The pricing page is public and shows the catalogue only (the product owner, 28-29 Sept
 * 2026: « tarification est une page publique comme pour Immo », « seules les offres
 * catalogues sont publiques »).
 *
 * 🔴 WHAT WOULD BREAK IT WITHOUT A SOUND: the route moved under `RequireAuth` (a visitor is
 * sent to the sign-in before seeing a price), an expired token bouncing the visitor away, or
 * a quoted offer drawn as a card with a price nobody agreed.
 */
describe('the pricing page', () => {
  it('is served before the signed-in guard', () => {
    const route = router.indexOf("path: '/pricing'")
    const guard = router.indexOf('element: <RequireAuth />')
    expect(route).toBeGreaterThan(-1)
    expect(route).toBeLessThan(guard)
  })

  it('is not left for the sign-in when a stale session answers 401', () => {
    expect(client).toMatch(/PUBLIC_DOORS = \[[^\]]*'\/pricing'/)
  })

  it('draws the catalogue only, and offers the quotation in one line', () => {
    expect(pricing).toContain('!plan.sur_devis')
    expect(pricing).toContain("setChosen('quote')")
    expect(signup).toContain('!p.sur_devis')
  })

  it('is reached from the sign-in page, which also opens the sign-up', () => {
    expect(login).toContain('to="/pricing"')
    expect(login).toContain('<SignupForm')
    expect(pricing).toContain('<LogoMark')
  })
})
