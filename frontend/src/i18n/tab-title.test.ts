/**
 * Every screen names its tab, and names it in the reader's language.
 *
 * 🔴 WHY A GUARD. The tab title is the only label of the interface that nobody looks at
 * while developing: one works with a single tab, already open, whose title is out of sight.
 * A screen added without its entry falls back on the brand alone, and that gets discovered
 * the day somebody has eight tabs and is looking for theirs.
 *
 * ⚠️ AND THE MAP IS DERIVED FROM THE MENU, not written a second time. The three sibling
 * products each keep a `PAGE_TITLES` by hand; a copied list is a list that drifts, and this
 * repository has already forgotten « invest » in four of them. This guard checks the rule
 * -- every route has a title -- and not the contents of a list.
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const SRC = join(__dirname, '..')
const router = readFileSync(join(SRC, 'router.tsx'), 'utf8')
const shell = readFileSync(join(SRC, 'components', 'layout', 'Shell.tsx'), 'utf8')

/** The routes the application really serves, read from the router. */
function routes(): string[] {
  return [...router.matchAll(/path:\s*'([^']+)'/g)]
    .map((match) => match[1])
    // `*` est le filet de sécurité (redirection), pas un écran ; `PASSWORD_ROUTE` est une
    // constante, reprise ci-dessous par son chemin littéral.
    .filter((path) => path !== '*')
}

/** Les chemins qui savent nommer leur onglet.
 *
 *  ⚠️ LE SHELL N'EST PAS LE SEUL A POUVOIR LE FAIRE. La connexion est rendue avant lui, donc
 *  hors de son effet ; elle pose son titre elle-meme. Une garde qui n'aurait regarde que le
 *  Shell aurait exige de l'y ajouter, c'est-a-dire d'y router un ecran qui n'y appartient
 *  pas. */
function titled(): string[] {
  const menu = [...shell.matchAll(/to:\s*'([^']+)'/g)].map((match) => match[1])
  const offMenu = [...shell.matchAll(/^\s*'(\/[^']*)':\s*'[a-z]/gm)].map((m) => m[1])
  // The public doors, rendered outside the shell: each one names its own tab.
  const doors = {
    '/login': 'Login.tsx',
    '/pricing': 'Pricing.tsx',
    '/set-password/:token': 'SetPassword.tsx',
  }
  const selfTitled = Object.entries(doors)
    .filter(([, file]) => readFileSync(join(SRC, 'pages', file), 'utf8').includes('document.title'))
    .map(([path]) => path)
  return [...menu, ...offMenu, ...selfTitled]
}

describe("le titre d'onglet", () => {
  it('couvre chaque route servie par le routeur', () => {
    const known = new Set(titled())
    // PASSWORD_ROUTE is declared as a constant in the router: its literal path
    // does not appear in a `path:`. It is covered by OFF_MENU_TITLES.
    const missing = routes().filter((path) => !known.has(path))

    expect(
      missing,
      `Ces écrans laisseraient l'onglet sur la marque seule : ${missing.join(', ')}. ` +
        `Ajoutez leur entrée au menu, ou à OFF_MENU_TITLES s'ils n'en ont pas.`,
    ).toEqual([])
  })

  it('sépare la marque du nom de page par une barre verticale, comme les produits frères', () => {
    expect(shell).toContain('`Le Comptoir Invest | ${')
  })

  it("se retraduit quand la langue change, et pas seulement quand la route change", () => {
    // ⚠️ The trap: `document.title` is set in an effect. Without the language in its
    // dependencies, switching language retranslates the whole screen and leaves the tab
    // behind -- the one place nobody thinks of checking.
    const effect = shell.slice(shell.indexOf('document.title'))
    const deps = effect.slice(effect.indexOf('}, ['), effect.indexOf('])') + 2)

    expect(deps).toContain('i18n.language')
  })
})
