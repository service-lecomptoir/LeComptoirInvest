/**
 * Chaque écran nomme son onglet, et le nomme dans la langue du lecteur.
 *
 * 🔴 POURQUOI UNE GARDE. Le titre d'onglet est la seule étiquette de l'interface que
 * personne ne regarde en développant : on travaille avec un onglet unique, déjà ouvert, dont
 * le titre est hors du champ de vision. Un écran ajouté sans son entrée retombe sur la marque
 * seule, et ça se découvre le jour où quelqu'un a huit onglets et cherche le sien.
 *
 * ⚠️ ET LA CARTE EST DÉRIVÉE DU MENU, pas écrite une seconde fois. Les trois produits frères
 * tiennent chacun un `PAGE_TITLES` à la main ; une liste recopiée est une liste qui dérive, et
 * ce dépôt a déjà oublié « invest » dans quatre d'entre elles. Cette garde vérifie la règle
 * — toute route a un titre — et non le contenu d'une liste.
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const SRC = join(__dirname, '..')
const router = readFileSync(join(SRC, 'router.tsx'), 'utf8')
const shell = readFileSync(join(SRC, 'components', 'layout', 'Shell.tsx'), 'utf8')

/** Les routes que l'application sert réellement, lues dans le routeur. */
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
  const login = readFileSync(join(SRC, 'pages', 'Login.tsx'), 'utf8')
  return [...menu, ...offMenu, ...(login.includes('document.title') ? ['/login'] : [])]
}

describe("le titre d'onglet", () => {
  it('couvre chaque route servie par le routeur', () => {
    const known = new Set(titled())
    // PASSWORD_ROUTE est déclaré comme constante dans le routeur : son chemin littéral
    // n'apparaît pas dans un `path:`. Il est couvert par OFF_MENU_TITLES.
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
    // ⚠️ Le piège : `document.title` est posé dans un effet. Sans la langue dans ses
    // dépendances, changer de langue retraduit tout l'écran et laisse l'onglet en arrière —
    // le seul endroit que personne ne pense à vérifier.
    const effect = shell.slice(shell.indexOf('document.title'))
    const deps = effect.slice(effect.indexOf('}, ['), effect.indexOf('])') + 2)

    expect(deps).toContain('i18n.language')
  })
})
