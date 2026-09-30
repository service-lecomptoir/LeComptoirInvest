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
// ⚠️ A LINE ENDS WITH OR WITHOUT A CARRIAGE RETURN: git checks the sources out in CRLF on
// Windows (`core.autocrlf`), and a closing tag compared with its trailing CR never
// matched, so a block ran to the end of the file and blamed the help of another form.
const EOL = /\r?\n/

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

describe('aucun mot en capitales à l’écran', () => {
  /**
   * 🔴 THE HOUSE RULE: no word in capitals in the interface. A `uppercase` class turned
   * « Offre en cours », the table headers and the side bar's sections into shouting
   * (customer recipe, 30 Sept 2026, twelve places). The one exception is a CODE that is
   * written in capitals anyway: a language code (`FR`, `EN`) on the same line.
   */
  it('pas de classe uppercase, sauf pour un code de langue', () => {
    const fautifs: string[] = []
    for (const file of walk(SRC, /\.tsx$/)) {
      withoutComments(readFileSync(file, 'utf8'))
        .split(EOL)
        .forEach((line, i) => {
          if (!/\buppercase\b/.test(line)) return
          if (/\{(l\.code|notice\.language)\}/.test(line)) return
          fautifs.push(`${file.slice(SRC.length + 1)}:${i + 1} ${line.trim()}`)
        })
    }
    expect(fautifs, `Texte en capitales : ${fautifs.join(' | ')}`).toEqual([])
  })
})

describe('aucune bulle du navigateur sur un formulaire', () => {
  /**
   * 🔴 THE BROWSER'S VALIDATION BUBBLE IS A NATIVE DIALOG, in the browser's language rather
   * than the page's: « Veuillez allonger ce texte » on the page where a new customer chooses
   * their password (customer recipe, 30 Sept 2026), gone as soon as one taps elsewhere.
   *
   * No exception: every form carries `noValidate` AND says what is wrong itself, under the
   * field (`lib/formCheck`). A form with `noValidate` and no check of its own would send
   * empty fields to the server, which is worse than the bubble.
   */
  const forms = () =>
    walk(SRC, /\.tsx$/)
      .map((file) => ({
        name: file.slice(SRC.length + 1).split(String.fromCharCode(92)).join('/'),
        source: withoutComments(readFileSync(file, 'utf8')),
      }))
      .filter(({ source }) => /<form\b/.test(source))

  /** What the rule refuses in one source: the offences, named. */
  function offences(name: string, source: string): string[] {
    const found: string[] = []
    for (const match of source.matchAll(/<form\b[^>]*>/g)) {
      if (!/\bnoValidate\b/.test(match[0])) found.push(`${name}: <form> sans noValidate`)
    }
    if (!/\buseFieldCheck\(/.test(source)) found.push(`${name}: aucun useFieldCheck()`)
    // A field marked required carries the place its message is shown.
    // An <Input> ends at its « /> » (an arrow `=>` inside it is no end); a <Field> opening
    // ends at the « > » that closes its line.
    for (const match of source.matchAll(/<(Input)\b[\s\S]*?\/>|<(Field)\b[\s\S]*?>[ \t]*\r?$/gm)) {
      const tag = match[0]
      if (/\brequired\b/.test(tag) && !/\berror=\{/.test(tag)) {
        found.push(`${name}: <${match[1] ?? match[2]}> requis sans error= (${tag.slice(0, 50)})`)
      }
    }
    return found
  }

  it('chaque formulaire porte noValidate et dit lui-même ce qui manque, sous le champ', () => {
    const all = forms()
    // The guard sees what it guards: the product has forms on a dozen screens.
    expect(all.length).toBeGreaterThan(8)
    const found = all.flatMap(({ name, source }) => offences(name, source))
    expect(found, found.join(' | ')).toEqual([])
  })

  it('la garde voit ce qu’elle interdit', () => {
    const bare = `<form onSubmit={go}><Input label="Nom" required /></form>`
    expect(offences('exemple.tsx', bare)).toEqual([
      'exemple.tsx: <form> sans noValidate',
      'exemple.tsx: aucun useFieldCheck()',
      'exemple.tsx: <Input> requis sans error= (<Input label="Nom" required />)',
    ])
    const right = `const { errors } = useFieldCheck()
<form noValidate onSubmit={go}><Input label="Nom" required error={errors.name} /></form>`
    expect(offences('exemple.tsx', right)).toEqual([])
  })
})
