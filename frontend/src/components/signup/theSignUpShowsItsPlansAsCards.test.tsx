import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import i18n from '@/i18n'
import type { PublicPlan } from '@/api'
import fr from '@/i18n/locales/fr.json'
import en from '@/i18n/locales/en.json'

import { PlanChoice } from './PlanChoice'
import { SignupForm } from './SignupForm'
import SIGNUP_FORM from './SignupForm.tsx?raw'

/**
 * The sign-up shows its plans the way Le Comptoir Immo does (the manager, 1 Oct 2026): cards
 * in a radio group, « Démo gratuite incluse » under a priced catalogue plan only, and an
 * opening sentence that says the demo before the plans.
 *
 * 🔴 WHICH PLAN INCLUDES THE DEMO IS ALICE'S ANSWER (`free_demo`, computed by
 * `plan_catalog.includes_free_demo` and relayed by the server). The rule was written thirteen
 * times in the nine fronts, in three spellings (1 Oct 2026): no screen writes it again.
 */

/** Every source file of the screens, tests aside: where a fourteenth copy would appear. */
const SOURCES = Object.entries(
  import.meta.glob<string>(['/src/**/*.{ts,tsx}', '!/src/**/*.test.{ts,tsx}'], { query: '?raw', import: 'default', eager: true }),
)

const PLAN: PublicPlan = {
  id: 'ess', name: 'Essentiel', description: null, investor_limit: 5,
  monthly_price: 29, overage_price: 0, tva_rate: 20, sur_devis: false, free_demo: true,
}
const FREE: PublicPlan = { ...PLAN, id: 'free', name: 'Découverte', monthly_price: 0, investor_limit: 1, free_demo: false }
const QUOTE: PublicPlan = { ...PLAN, id: 'quote', name: 'Sur mesure', monthly_price: 90, sur_devis: true, free_demo: false }

const count = (html: string, text: string) => html.split(text).length - 1
const LOCALES: Record<string, any> = { fr, en }

describe('the sign-up plans', () => {
  it('says the demo under a priced catalogue plan, never under a free plan nor a quotation', async () => {
    await i18n.changeLanguage('fr')
    const html = renderToStaticMarkup(
      <PlanChoice plans={[FREE, PLAN, QUOTE]} value="" onChange={() => undefined} hint="Aide" />,
    )
    expect(count(html, 'Démo gratuite incluse')).toBe(1)
    const paid = html.indexOf('Essentiel')
    expect(html.slice(paid, html.indexOf('Sur mesure'))).toContain('Démo gratuite incluse')
    for (const [lang, catalogue] of Object.entries(LOCALES)) {
      expect(catalogue.pricing.freeDemo, `${lang}: no number of days`).not.toMatch(/\d/)
    }
  })

  it("follows Alice's answer, not the price", async () => {
    await i18n.changeLanguage('fr')
    // A priced plan Alice says has no demo shows none; a plan she says has one shows it.
    const html = renderToStaticMarkup(
      <PlanChoice plans={[{ ...PLAN, free_demo: false }, { ...FREE, free_demo: true }]} value="" onChange={() => undefined} hint="Aide" />,
    )
    expect(count(html, 'Démo gratuite incluse')).toBe(1)
    expect(html.indexOf('Démo gratuite incluse')).toBeGreaterThan(html.indexOf('Découverte'))
  })

  it('has no screen deciding the demo itself: each mention is under `free_demo`', () => {
    expect(SOURCES.length).toBeGreaterThan(20)
    const mentions = SOURCES.filter(([, src]) => src.includes("t('pricing.freeDemo')"))
    expect(mentions.map(([path]) => path).sort()).toEqual(['/src/components/signup/PlanChoice.tsx', '/src/pages/Pricing.tsx'])
    for (const [path, src] of mentions) {
      for (const m of src.matchAll(/t\('pricing\.freeDemo'\)/g)) {
        const at = m.index ?? 0
        expect(src.slice(Math.max(0, at - 200), at), path).toMatch(/\.free_demo && \(?\s*<[^>]*>\{$/)
      }
    }
    for (const [path, src] of SOURCES) expect(src, path).not.toMatch(/showsFreeDemo|includesFreeDemo|offersDemo/)
  })

  it('is a radio group: one radio per plan, under a legend, the help tied to it', async () => {
    await i18n.changeLanguage('fr')
    const html = renderToStaticMarkup(
      <PlanChoice plans={[FREE, PLAN]} value="ess" onChange={() => undefined} hint="Aide" />,
    )
    expect(count(html, 'type="radio"')).toBe(2)
    expect(html).toMatch(/<fieldset aria-describedby="[^"]+"/)
    expect(html).toContain('<legend')
    expect(count(html, 'checked=""')).toBe(1)
    expect(html).toContain('peer-focus-visible:outline')
  })

  it('opens on the demo for an account, on the quotation for a management company', async () => {
    for (const [lang, catalogue] of Object.entries(LOCALES)) {
      expect(catalogue.signup.intro, lang).toMatch(/démo|demo/i)
      expect(catalogue.signup.intro, lang).not.toMatch(/\d/)
      expect(catalogue.signup.introQuote, lang).not.toMatch(/démo|demo/i)
    }
    await i18n.changeLanguage('fr')
    expect(renderToStaticMarkup(<SignupForm />)).toContain(fr.signup.intro.replace(/'/g, '&#x27;'))
    const quoted = renderToStaticMarkup(<SignupForm quote />)
    expect(quoted).not.toContain('type="radio"')
    expect(quoted).not.toContain('Démo gratuite incluse')
  })

  it('has no plan dropdown left', () => {
    expect(SIGNUP_FORM).toContain('<PlanChoice')
    expect(SIGNUP_FORM).not.toMatch(/value=\{draft\.plan_id\}\s*onChange=\{\(plan_id\) => set\(\{ plan_id \}\)\}\s*placeholder/)
    expect(SIGNUP_FORM).not.toContain("t('signup.choosePlan')")
  })
})
