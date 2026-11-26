/**
 * Every screen the router serves has its card in the guide, and every card says something.
 *
 * 🔴 WHY A GUARD. The guide is written by hand, screen by screen, and a screen added next
 * month will not think of it: the reader then looks for help about a tab the guide does
 * not know. Le Comptoir Immo holds the same rule over its generated guide
 * (`guideExplainsEverySection.test.ts`); here the list is read from the router itself.
 */
import { describe, expect, it } from 'vitest'
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { GUIDE_ROUTE, GUIDE_SECTIONS, type Audience } from './guide'

const SRC = join(__dirname, '..')
const read = (...path: string[]) => readFileSync(join(SRC, ...path), 'utf8')
const router = read('router.tsx')
// 🔴 EVERY LANGUAGE OF THE PRODUCT, READ FROM ITS CATALOGUES (French and English today): a
// language added tomorrow is checked from its first commit, without anybody editing this list.
const LANGS = readdirSync(join(SRC, 'i18n', 'locales'))
  .filter((name) => name.endsWith('.json'))
  .map((name) => name.replace(/\.json$/, ''))

/** The doors outside the signed-in shell (sign-in, the public pricing page), and the safety
 *  net: none is a screen to explain. */
const NOT_SCREENS = new Set(['*', '/login', '/pricing', '/privacy', '/set-password/:token', GUIDE_ROUTE])

function screens(): string[] {
  const paths = [...router.matchAll(/path:\s*'([^']+)'/g)].map((m) => m[1])
  // `PROFILE_ROUTE` is a constant in the router; its literal path is read from it.
  const profile = /const PROFILE_ROUTE = '([^']+)'/.exec(router)?.[1]
  return [...paths, ...(profile ? [profile] : [])].filter((p) => !NOT_SCREENS.has(p))
}

const cards = GUIDE_SECTIONS.flatMap((section) => section.cards)

interface MenuEntry {
  route: string
  /** The catalogue key the menu shows. */
  label: string
  /** Absent: every account sees the entry. */
  audience?: Audience
}

const ITEM = /\{\s*to:\s*'([^']*)',\s*key:\s*'([^']+)'/g

/**
 * Every entry of the menus, read from their sources: the rail (`Shell.tsx`, `FUND_NAV` for
 * whoever sees the whole fund, `INVESTOR_NAV` for an investor) and the account menu
 * (`ProfileMenu.tsx`, a `navigate` followed by its label; the guide itself excluded).
 */
function menuEntries(): MenuEntry[] {
  const shell = read('components', 'layout', 'Shell.tsx')
  const fundAt = shell.indexOf('const FUND_NAV')
  const investorAt = shell.indexOf('const INVESTOR_NAV')
  const rail = (from: number, to: number, audience: Audience) =>
    [...shell.slice(from, to).matchAll(ITEM)].map((m) => ({ route: m[1], label: m[2], audience }))
  const end = shell.indexOf('\n]', investorAt)
  const account = [...read('components', 'layout', 'ProfileMenu.tsx').matchAll(/(seesWholeFund\s*&&\s*\(\s*)?<button[\s\S]*?navigate\('([^']+)'\)[\s\S]*?\{t\('([^']+)'\)\}/g)]
    .map((m) => ({ route: m[2], label: m[3], audience: m[1] ? ('fund' as const) : undefined }))
    .filter((entry) => entry.route !== GUIDE_ROUTE)
  return [...rail(fundAt, investorAt, 'fund'), ...rail(investorAt, end, 'investor'), ...account]
}

/** The router's screens kept for one audience (`FundOnly`, `InvestorOnly`). */
function reservedScreens(): Map<string, Audience> {
  const kept = new Map<string, Audience>()
  for (const m of router.matchAll(/path:\s*'([^']+)',\s*element:\s*<(FundOnly|InvestorOnly)>/g)) {
    kept.set(m[1], m[2] === 'FundOnly' ? 'fund' : 'investor')
  }
  return kept
}

/** The cards an audience reads, as `Guide.tsx` filters them. */
const cardsFor = (audience: Audience) => cards.filter((card) => !card.audience || card.audience === audience)

function lookup(catalogue: unknown, key: string): unknown {
  return key.split('.').reduce<unknown>(
    (node, part) => (node && typeof node === 'object' ? (node as Record<string, unknown>)[part] : undefined),
    catalogue,
  )
}

describe('the guide', () => {
  it('finds screens to inspect', () => {
    // A guard reading nothing would always pass: a renamed router would do exactly that.
    expect(screens().length).toBeGreaterThan(10)
  })

  it('has a card for every screen of the router', () => {
    const covered = new Set(cards.map((card) => card.route))
    const missing = screens().filter((path) => !covered.has(path))
    expect(missing, `Ces écrans n'ont pas de carte dans le guide (lib/guide.ts) : ${missing.join(', ')}`).toEqual([])
  })

  it('gives each audience its own card for a path both of them open', () => {
    // `/` is the fund's dashboard or the investor's portfolio: one card each, never two for
    // the same reader.
    const seen = new Set<string>()
    const twice = cards
      .filter((card) => {
        const key = `${card.route} ${card.audience ?? 'all'}`
        const repeated = seen.has(key)
        seen.add(key)
        return repeated
      })
      .map((card) => card.route)
    expect(twice).toEqual([])
    expect(cards.filter((card) => card.route === '/').map((card) => card.audience).sort()).toEqual([
      'fund',
      'investor',
    ])
  })

  it('finds menu entries to inspect, for the fund and for an investor', () => {
    const entries = menuEntries()
    expect(entries.filter((entry) => entry.audience === 'fund').length).toBeGreaterThan(5)
    expect(entries.filter((entry) => entry.audience === 'investor').length).toBeGreaterThan(3)
    expect(entries.map((entry) => entry.route)).toEqual(expect.arrayContaining(['/profile', '/billing']))
    expect(reservedScreens().get('/billing')).toBe('fund')
  })

  it('has a card for every entry of the menu, for the reader who sees it, under its label', () => {
    const missing: string[] = []
    for (const entry of menuEntries()) {
      for (const audience of entry.audience ? [entry.audience] : (['fund', 'investor'] as const)) {
        if (!cardsFor(audience).some((card) => card.route === entry.route && card.title === entry.label)) {
          missing.push(`${entry.route} (${entry.label}, ${audience})`)
        }
      }
    }
    expect(missing, `Ces entrées du menu n'ont pas leur carte dans le guide (lib/guide.ts) : ${missing.join(', ')}`).toEqual([])
  })

  it('never shows a reader the card of a screen kept for the other audience', () => {
    const wrong: string[] = []
    for (const [route, audience] of reservedScreens()) {
      for (const card of cards.filter((c) => c.route === route)) {
        if (card.audience !== audience) wrong.push(`${route} (${card.id})`)
      }
    }
    expect(wrong).toEqual([])
  })

  it('has no card for a screen that no longer exists', () => {
    const served = new Set(screens())
    const stale = cards.filter((card) => !served.has(card.route)).map((card) => card.route)
    expect(stale).toEqual([])
  })

  it('says what each screen is for and how to use it, in every language', async () => {
    expect(LANGS).toEqual(expect.arrayContaining(['fr', 'en']))
    const empty: string[] = []
    for (const lang of LANGS) {
      const catalogue = (await import(`../i18n/locales/${lang}.json`)).default
      for (const card of cards) {
        for (const key of [card.title, `guide.cards.${card.id}.what`, `guide.cards.${card.id}.how`]) {
          const value = lookup(catalogue, key)
          if (typeof value !== 'string' || !value.trim()) empty.push(`${lang}: ${key}`)
        }
      }
    }
    expect(empty).toEqual([])
  })

  it('is offered in the account menu, as in the sibling products', () => {
    const menu = readFileSync(join(SRC, 'components', 'layout', 'ProfileMenu.tsx'), 'utf8')
    expect(menu).toContain(`navigate('${GUIDE_ROUTE}')`)
    expect(router).toContain(`path: '${GUIDE_ROUTE}'`)
  })
})
