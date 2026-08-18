/**
 * The two catalogues hold the SAME keys, and the English one is not the French one.
 *
 * ⚠️ THE SECOND CHECK IS THE ONE THAT EARNS ITS KEEP. Comparing key sets passes happily
 * over an `en.json` whose values were copied from `fr.json` — which is exactly what a
 * generated catalogue looks like, and exactly what the sister product shipped: without an
 * LLM key its `i18n:sync` writes the French text into the English file and the completeness
 * check goes green. So this one also refuses an English string that is byte-for-byte its
 * French counterpart.
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = dirname(fileURLToPath(import.meta.url))
const load = (lang) =>
  JSON.parse(readFileSync(join(here, '..', 'src/i18n/locales', `${lang}.json`), 'utf8'))

const flatten = (obj, prefix = '') =>
  Object.entries(obj).flatMap(([k, v]) =>
    v && typeof v === 'object' ? flatten(v, `${prefix}${k}.`) : [[`${prefix}${k}`, v]],
  )

const fr = Object.fromEntries(flatten(load('fr')))
const en = Object.fromEntries(flatten(load('en')))

const missing = Object.keys(fr).filter((k) => !(k in en))
const extra = Object.keys(en).filter((k) => !(k in fr))

// ⚠️ THE CRITERION IS THE WORD COUNT, NOT THE LENGTH. « Distributions » is thirteen
// characters and is the same word in both languages; a length threshold flagged it and
// would have taught whoever hit it to widen the exception list until the check meant
// nothing. Two languages agreeing on a WHOLE SENTENCE is what evidences a copy, and three
// words is where a sentence starts.
const words = (value) => String(value).trim().split(/\s+/).length
const copied = Object.keys(fr).filter((k) => k in en && fr[k] === en[k] && words(fr[k]) > 2)

let failed = false
const report = (title, keys, render = (k) => `  ${k}`) => {
  if (!keys.length) return
  console.error(`${title} (${keys.length}) :`)
  keys.forEach((k) => console.error(render(k)))
  failed = true
}

report('Manquent dans en.json', missing)
report('En trop dans en.json', extra)
report('Recopies du francais dans en.json', copied, (k) => `  ${k} = ${JSON.stringify(fr[k])}`)

if (failed) process.exit(1)
console.log(`i18n : ${Object.keys(fr).length} cles, deux catalogues alignes et distincts.`)
