import { describe, expect, it } from 'vitest'
import SOURCE from './pageLeaving.ts?raw'

/**
 * The owner, 9 Nov 2026: « Connexion au serveur impossible » on the iPhone, at every click
 * on « Ajouter un moyen de paiement », and « on a ça potentiellement dans toutes les
 * applis ». `pageLeaving.ts` is the same file in every product; this guard is the same in
 * every product too.
 */
describe('the copy of every product', () => {
  // FNV-1a over the text with LF line ends: a checkout with CRLF reads the same.
  const fingerprint = (text: string): string => {
    let hash = 0x811c9dc5
    for (const char of text.replace(/\r\n/g, '\n')) {
      for (let i = 0; i < char.length; i++) {
        hash ^= char.charCodeAt(i)
        hash = Math.imul(hash, 0x01000193) >>> 0
      }
    }
    return hash.toString(16).padStart(8, '0')
  }

  it('is the shared pageLeaving.ts: change one, change them all', () => {
    expect(fingerprint(SOURCE)).toBe('0b7d7c82')
  })
})
