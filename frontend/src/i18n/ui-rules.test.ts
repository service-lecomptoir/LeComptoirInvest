/**
 * Three interface rules that nothing recalls at the moment one breaks them.
 *
 * 🔴 WHY GUARDS AND NOT A CONVENTION. The three defects below were reported by the user,
 * screenshot in hand, after I had introduced them nine, ten and one time. None of them
 * breaks anything: the product works, the tests pass, and the screen is simply less
 * readable or carries a mark we do not want. That is exactly the category of defect that a
 * review never catches, because there is nothing to see as long as one does not look at the
 * screen.
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

/** Strips the comments: the rule targets the text SEEN, not the notes of the code. */
function withoutComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
}

describe('pas de tiret cadratin dans ce qui est vu', () => {
  /**
   * ⚠️ THE MINUS SIGN U+2212 STAYS ALLOWED, and that is not an exception out of
   * complacency: it is arithmetic, not punctuation. Confusing it with a dash would replace
   * subtractions with commas and make the formulas wrong instead of readable.
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
   * 🔴 THE DEFECT, EXACTLY. In an `items-end` row, the cells align by their BOTTOM. A field
   * that carries a hint under it is therefore taller than its neighbours, and its label
   * rises: the line visibly breaks. And even when every field carries one, two hints of
   * different lengths do not wrap over the same number of lines, so the alignment breaks
   * all the same.
   *
   * The rule is simple and has no useful exception: the hint goes UNDER the row, where it
   * reads better anyway. A whole sentence never had its place under a field two centimetres
   * wide.
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
   * 🔴 `window.confirm`, `window.alert` and `window.prompt` are forbidden. It is not a
   * matter of taste: they can display neither an amount, nor a name, nor tell « annuler »
   * from « détruire »; they block the browser's thread; some browsers suppress them when
   * they come from a background tab; and they carry the name of the domain rather than that
   * of the product.
   *
   * The product has `confirmDialog()` for that. This guard exists because a `window.prompt`
   * had already slipped into the treasury screen, where it asked for a subscription id
   * without being able to show the amount about to be charged.
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
