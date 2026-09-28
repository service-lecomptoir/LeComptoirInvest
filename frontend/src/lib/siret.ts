// Validation and verification of French company registration numbers (9 or 14 digits).
// - Offline validation: the format plus the Luhn key (with the postal-service exception).
// - Verification that it really exists, and what the register says: asked to this
//   product's server, which relays to the console (the national company-search API).
// Everything is best effort: an unavailable network never blocks data entry.
//
// Same rule and same API as the sibling products (Le Comptoir Immo and RH, `lib/siret.ts`):
// one need, one code across the platform.
import { publicApi } from '@/api'

/** Keeps the digits only, 14 at most (the length of a full number). */
export function cleanSiren(v: string): string {
  return (v || '').replace(/\D/g, '').slice(0, 14)
}

/** « 552 032 534 » or « 552 032 534 00703 »: the digits by groups, as INSEE prints them. */
export function groupSiren(v: string): string {
  const d = cleanSiren(v)
  const groups = [d.slice(0, 3), d.slice(3, 6), d.slice(6, 9), d.slice(9, 14)]
  return groups.filter(Boolean).join(' ')
}

/** Luhn key over a string of digits. */
function luhn(num: string): boolean {
  let sum = 0
  let alt = false
  for (let i = num.length - 1; i >= 0; i--) {
    let n = num.charCodeAt(i) - 48
    if (alt) {
      n *= 2
      if (n > 9) n -= 9
    }
    sum += n
    alt = !alt
  }
  return sum % 10 === 0
}

export type SirenKind = 'siren' | 'siret' | null

/**
 * Validates the FORMAT (length + Luhn key) of a 9- or 14-digit number.
 * The postal service (SIREN 356000000): some of its numbers do not satisfy Luhn yet are
 * valid when the sum of their digits is a multiple of 5, an acceptance ON TOP of Luhn.
 */
export function checkSirenSiret(v: string): { ok: boolean; kind: SirenKind } {
  const d = cleanSiren(v)
  const digitSum = (s: string) => s.split('').reduce((a, c) => a + (c.charCodeAt(0) - 48), 0)
  if (d.length === 9) {
    const laPoste = d === '356000000' && digitSum(d) % 5 === 0
    return { ok: luhn(d) || laPoste, kind: 'siren' }
  }
  if (d.length === 14) {
    const laPoste = d.startsWith('356000000') && digitSum(d) % 5 === 0
    return { ok: luhn(d) || laPoste, kind: 'siret' }
  }
  return { ok: false, kind: null }
}

export type LookupStatus = 'found' | 'not_found' | 'error'

/** What the register says of a company: enough to fill a form, nothing to sign. */
export interface SirenLookup {
  status: LookupStatus
  name?: string
  street?: string
  postcode?: string
  city?: string
}

/**
 * Checks that a registration number really exists in the national register, and brings
 * back what the register says. `error` (and not `not_found`) when nothing answers, so
 * that « not found » is never displayed wrongly.
 */
export async function lookupSirenSiret(v: string, signal?: AbortSignal): Promise<SirenLookup> {
  const d = cleanSiren(v)
  if (d.length !== 9 && d.length !== 14) return { status: 'not_found' }
  try {
    const { data } = await publicApi.company(d, signal)
    if (data.status === 'found') {
      return {
        status: 'found',
        name: data.name ?? undefined,
        street: data.street ?? undefined,
        postcode: data.zip_code ?? undefined,
        city: data.city ?? undefined,
      }
    }
    return { status: data.status === 'not_found' || data.status === 'invalid' ? 'not_found' : 'error' }
  } catch {
    return { status: 'error' }
  }
}
