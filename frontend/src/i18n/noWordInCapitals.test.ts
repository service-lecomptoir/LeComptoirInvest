/**
 * No word in capitals in what the catalogues say, and French written with its accents.
 *
 * 🔴 REPORTED ON 1 OCT 2026. The `uppercase` class was already refused (`ui-rules.test`),
 * but the catalogues still shouted by hand: « l'année du PAIEMENT », « le virement
 * SORTANT », « C'est un ÉVÉNEMENT », the same in English; and the notice shown when the
 * sending address is missing read « n'est pas configure », « Systeme », « hameconnage ».
 *
 * The one exception to the capitals is an ACRONYM, written in capitals in every text that
 * uses it: the list below is closed, and a new one is added here on purpose.
 */
import { describe, expect, it } from 'vitest'
import fr from './locales/fr.json'
import en from './locales/en.json'

const ACRONYMS = new Set([
  'BIC', 'CAMT', 'DPI', 'FAQ', 'HTTPS', 'IBAN', 'JSON', 'PDF', 'QR', 'RVPI', 'SEPA', 'SIREN',
  'SIRET', 'TVA', 'TVPI', 'VAT',
])

function flat(node: unknown, path = ''): [string, string][] {
  if (typeof node === 'string') return [[path, node]]
  if (node && typeof node === 'object') {
    return Object.entries(node as Record<string, unknown>).flatMap(([k, v]) => flat(v, path ? `${path}.${k}` : k))
  }
  return []
}

/** The words of two capitals or more that are not a known acronym. */
function shouted(text: string): string[] {
  return (text.match(/(?<![\p{L}\p{N}])\p{Lu}{2,}(?![\p{L}\p{N}])/gu) ?? []).filter((w) => !ACRONYMS.has(w))
}

describe('the catalogues', () => {
  it('write no word in capitals, acronyms aside', () => {
    const found = [...flat(fr).map(([k, v]) => [`fr:${k}`, v]), ...flat(en).map(([k, v]) => [`en:${k}`, v])]
      .flatMap(([k, v]) => shouted(v).map((w) => `${k} ${w}`))
    expect(found, found.join(' | ')).toEqual([])
  })

  it('the guard sees what it forbids', () => {
    expect(shouted("L'année du PAIEMENT, un ÉVÉNEMENT")).toEqual(['PAIEMENT', 'ÉVÉNEMENT'])
    expect(shouted('Le fichier PDF du virement SEPA, en E-mail')).toEqual([])
  })

  it('write French with its accents in the sending notice', () => {
    expect(fr.notice.sendingNotSetUp).toBe("L'envoi d'e-mail n'est pas configuré")
    for (const word of ['expédition', 'renseignée', 'Système', 'portée', 'envoyé', 'hameçonnage', 'enregistré', 'notifié', 'été']) {
      expect(fr.notice.sendingNotSetUpHint).toContain(word)
    }
    expect(en.notice.sendingNotSetUpHint).toContain('« Système de communication »')
  })
})
