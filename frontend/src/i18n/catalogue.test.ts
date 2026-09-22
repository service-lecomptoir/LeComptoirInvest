/**
 * No screen carries its own French, and the two catalogues stay honest.
 *
 * 🔴 WHY A GUARD AND NOT A CONVENTION. Every screen in this product was written in French
 * first and moved into the catalogue afterwards. That move is a one-off effort; keeping it
 * is not. The twelfth screen somebody adds under time pressure will hold a hard-coded
 * label, it will work, it will be reviewed, and the product will be bilingual everywhere
 * except there — which is the state nobody ever notices, because the person adding it
 * reads French.
 *
 * ⚠️ WHAT IS DETECTED IS THE ACCENT, NOT THE LANGUAGE. Recognising French would need a
 * dictionary, and a dictionary is a list that is always narrower than its rule — this
 * repository lost five stored values to exactly that on 18 August. An accented character
 * inside a string or a piece of JSX text is unambiguous evidence, and every French label
 * this product shows contains one somewhere in its screen.
 *
 * The remaining hole is honest and named: « Total », « Distributions », « Instrument » —
 * French without an accent — would slip through. `i18n:check` catches the other half by
 * refusing an English catalogue entry identical to its French counterpart.
 */
import { describe, expect, it } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import fr from './locales/fr.json'
import en from './locales/en.json'
import { copiedKeys } from './copyRule'

const SRC = join(__dirname, '..')
const ACCENTED = /[àâäçéèêëîïôöùûüÿœÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŸŒ]/

/** Files whose accented text is data, or a message meant for a developer.
 *
 *  ⚠️ EVERY TEST FILE IS EXEMPT, and that is a rule, not a convenience: the message of an
 *  assertion speaks to whoever reads the failure, never to a user. The first version named
 *  the files one by one, and the guard fired on the very next test I wrote. A list that has
 *  to be lengthened on every addition is a list that ends up being emptied. */
const EXEMPT = new Set(['fr.json', 'en.json', 'index.ts'])
const IS_TEST = /\.test\.tsx?$/

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) return walk(full)
    if (EXEMPT.has(entry) || IS_TEST.test(entry)) return []
    return /\.(ts|tsx)$/.test(entry) ? [full] : []
  })
}

/** Remove comments, so an English comment quoting « une phrase » is not a finding. */
function withoutComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1')
}

const flatten = (obj: Record<string, unknown>, prefix = ''): [string, unknown][] =>
  Object.entries(obj).flatMap(([k, v]) =>
    v && typeof v === 'object'
      ? flatten(v as Record<string, unknown>, `${prefix}${k}.`)
      : [[`${prefix}${k}`, v] as [string, unknown]],
  )

describe('the interface is translated, not written twice', () => {
  it('no source file holds French text of its own', () => {
    const offenders: string[] = []
    for (const file of walk(SRC)) {
      const body = withoutComments(readFileSync(file, 'utf8'))
      body.split('\n').forEach((line, i) => {
        if (ACCENTED.test(line)) {
          offenders.push(`${file.slice(SRC.length + 1)}:${i + 1}  ${line.trim().slice(0, 90)}`)
        }
      })
    }
    expect(offenders, `Ces lignes portent du texte français hors catalogue :\n${offenders.join('\n')}`)
      .toEqual([])
  })

  it('both catalogues hold the same keys', () => {
    const frKeys = flatten(fr as Record<string, unknown>).map(([k]) => k).sort()
    const enKeys = flatten(en as Record<string, unknown>).map(([k]) => k).sort()
    expect(enKeys).toEqual(frKeys)
  })

  it('no English entry is a copy of its French counterpart', () => {
    const frMap = Object.fromEntries(flatten(fr as Record<string, unknown>))
    const enMap = Object.fromEntries(flatten(en as Record<string, unknown>))
    // 🔴 THE RULE LIVES IN `copyRule.ts`, AND NOT HERE. It was written twice: here
    // and in `scripts/i18n-check.mjs`. Adding `brand.full` brought both down, one
    // after the other -- and the first thing one does in front of a red guard one
    // believes to have fixed is to doubt the guard.
    const copied = copiedKeys(frMap, enMap)
    expect(copied, `Recopiés du français : ${copied.join(', ')}`).toEqual([])
  })
})
