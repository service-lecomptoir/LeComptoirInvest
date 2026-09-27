/**
 * Every screen the router serves has its card in the guide, and every card says something.
 *
 * 🔴 WHY A GUARD. The guide is written by hand, screen by screen, and a screen added next
 * month will not think of it: the reader then looks for help about a tab the guide does
 * not know. Le Comptoir Immo holds the same rule over its generated guide
 * (`guideExplainsEverySection.test.ts`); here the list is read from the router itself.
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { GUIDE_ROUTE, GUIDE_SECTIONS } from './guide'

const SRC = join(__dirname, '..')
const router = readFileSync(join(SRC, 'router.tsx'), 'utf8')
// This product speaks French and English.
const LANGS = ['fr', 'en']

/** The doors outside the signed-in shell, and the safety net: none is a screen to explain. */
const NOT_SCREENS = new Set(['*', '/login', '/set-password/:token', GUIDE_ROUTE])

function screens(): string[] {
  const paths = [...router.matchAll(/path:\s*'([^']+)'/g)].map((m) => m[1])
  // `PROFILE_ROUTE` is a constant in the router; its literal path is read from it.
  const profile = /const PROFILE_ROUTE = '([^']+)'/.exec(router)?.[1]
  return [...paths, ...(profile ? [profile] : [])].filter((p) => !NOT_SCREENS.has(p))
}

const cards = GUIDE_SECTIONS.flatMap((section) => section.cards)

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

  it('has no card for a screen that no longer exists', () => {
    const served = new Set(screens())
    const stale = cards.filter((card) => !served.has(card.route)).map((card) => card.route)
    expect(stale).toEqual([])
  })

  it('says what each screen is for and how to use it, in every language', async () => {
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
