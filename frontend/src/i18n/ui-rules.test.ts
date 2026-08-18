/**
 * Trois règles d'interface que rien ne rappelle au moment où on les enfreint.
 *
 * 🔴 POURQUOI DES GARDES ET PAS UNE CONVENTION. Les trois défauts ci-dessous ont été
 * signalés par le user, capture d'écran à l'appui, après que je les ai introduits neuf,
 * dix et une fois. Aucun ne casse quoi que ce soit : le produit fonctionne, les tests
 * passent, et l'écran est simplement moins lisible ou porte une marque qu'on ne veut pas.
 * C'est exactement la catégorie de défaut qu'une relecture ne rattrape jamais, parce qu'il
 * n'y a rien à voir tant qu'on ne regarde pas l'écran.
 */
import { describe, expect, it } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

const SRC = join(__dirname, '..')
const EOL = String.fromCharCode(10)

function walk(dir: string, ext: RegExp): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) return walk(full, ext)
    return ext.test(entry) ? [full] : []
  })
}

/** Retire les commentaires : la règle vise le texte VU, pas les notes du code. */
function withoutComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
}

describe('pas de tiret cadratin dans ce qui est vu', () => {
  /**
   * ⚠️ LE SIGNE MOINS U+2212 RESTE AUTORISÉ, et ce n'est pas une exception de complaisance :
   * c'est de l'arithmétique, pas de la ponctuation. Le confondre avec un tiret remplacerait
   * des soustractions par des virgules et rendrait les formules fausses au lieu de lisibles.
   */
  const INTERDITS = /[—–]/

  it("les deux catalogues n'en contiennent aucun", () => {
    for (const lang of ['fr', 'en']) {
      const raw = readFileSync(join(SRC, `i18n/locales/${lang}.json`), 'utf8')
      const fautifs = raw
        .split(EOL)
        .map((l, i) => [i + 1, l] as const)
        .filter(([, l]) => INTERDITS.test(l))
        .map(([n, l]) => `${lang}.json:${n} ${l.trim()}`)
      expect(
        fautifs,
        `Remplacer par deux points, une virgule, ou des parenthèses : ${fautifs.join(' | ')}`,
      ).toEqual([])
    }
  })

  it("aucun écran n'en écrit un en dur", () => {
    const fautifs: string[] = []
    const fichiers = walk(join(SRC, 'pages'), /\.tsx$/).concat(
      walk(join(SRC, 'components'), /\.tsx$/),
      walk(join(SRC, 'lib'), /\.ts$/),
    )
    for (const file of fichiers) {
      withoutComments(readFileSync(file, 'utf8'))
        .split(EOL)
        .forEach((line, i) => {
          if (INTERDITS.test(line)) {
            fautifs.push(`${file.slice(SRC.length + 1)}:${i + 1} ${line.trim()}`)
          }
        })
    }
    expect(fautifs, `Tiret visible : ${fautifs.join(' | ')}`).toEqual([])
  })
})

describe('une aide ne vit pas dans une barre alignée en bas', () => {
  /**
   * 🔴 LE DÉFAUT, EXACTEMENT. Dans une rangée `items-end`, les cellules s'alignent par leur
   * BAS. Un champ qui porte une aide sous lui est donc plus haut que ses voisins, et son
   * libellé remonte : la ligne se casse visiblement. Et même quand tous les champs en
   * portent une, deux aides de longueurs différentes ne se replient pas sur le même nombre
   * de lignes, donc l'alignement casse quand même.
   *
   * La règle est simple et n'a pas d'exception utile : l'aide se met SOUS la rangée, où
   * elle se lit d'ailleurs mieux. Une phrase entière n'a jamais eu sa place sous un champ
   * de deux centimètres.
   */
  it('aucun hint ne se trouve dans un bloc items-end', () => {
    const fautifs: string[] = []
    for (const file of walk(join(SRC, 'pages'), /\.tsx$/)) {
      const lines = readFileSync(file, 'utf8').split(EOL)
      lines.forEach((line, i) => {
        if (!line.includes('items-end')) return
        const indent = line.length - line.trimStart().length
        const tag = line.includes('<form') ? 'form' : 'div'
        const close = `${' '.repeat(indent)}</${tag}>`
        let end = lines.length
        for (let j = i + 1; j < lines.length; j++) {
          if (lines[j] === close) {
            end = j
            break
          }
        }
        for (let j = i; j < end; j++) {
          if (/^\s*hint=\{/.test(lines[j])) {
            fautifs.push(`${file.slice(SRC.length + 1)}:${j + 1} ${lines[j].trim()}`)
          }
        }
      })
    }
    expect(
      fautifs,
      `Aides cassant leur rangée, à déplacer sous le bloc : ${fautifs.join(' | ')}`,
    ).toEqual([])
  })
})

describe("aucune boîte du navigateur ne pose de question à l'utilisateur", () => {
  /**
   * 🔴 `window.confirm`, `window.alert` et `window.prompt` sont interdits. Ce n'est pas une
   * question de goût : elles ne savent afficher ni un montant, ni un nom, ni distinguer
   * « annuler » de « détruire » ; elles bloquent le fil du navigateur ; certains navigateurs
   * les suppriment quand elles viennent d'un onglet en arrière-plan ; et elles portent le
   * nom du domaine plutôt que celui du produit.
   *
   * Le produit a `confirmDialog()` pour cela. Cette garde existe parce qu'un `window.prompt`
   * s'était déjà glissé dans l'écran de trésorerie, où il demandait un identifiant de
   * souscription sans pouvoir montrer le montant qu'on allait imputer.
   */
  it('ni confirm, ni alert, ni prompt', () => {
    const fautifs: string[] = []
    for (const file of walk(SRC, /\.(ts|tsx)$/)) {
      if (/\.test\.tsx?$/.test(file)) continue
      withoutComments(readFileSync(file, 'utf8'))
        .split(EOL)
        .forEach((line, i) => {
          if (/window\.(confirm|alert|prompt)\s*\(/.test(line)) {
            fautifs.push(`${file.slice(SRC.length + 1)}:${i + 1} ${line.trim()}`)
          }
        })
    }
    expect(fautifs, `Utiliser confirmDialog() : ${fautifs.join(' | ')}`).toEqual([])
  })
})
