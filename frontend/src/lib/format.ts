import i18n from '@/i18n'
import { dayOf } from './day'

/**
 * Showing money, when the fund holds several currencies.
 *
 * 🔴 THE CURRENCY IS NEVER ASSUMED. Every amount this product handles carries its own,
 * because the treasury invariant holds per currency and a total mixing euros and CFA
 * francs is a balance nowhere. A formatter defaulting to EUR would print « 3 000 000 € »
 * over an XOF figure, and the number would be right while the label lied.
 *
 * ⚠️ AND THE MINOR UNIT IS NOT ALWAYS TWO. XOF has none: « 1 000,00 FCFA » is not a
 * currency amount, it is a euro habit applied to somebody else's money.
 */

/**
 * 🔴 THE ACTIVE LANGUAGE, NOT `fr-FR` HARD-CODED. The first version documented at length
 * that one must NEVER assume the currency... while hard-coding the locale three lines below.
 * Seen on screen on 18 August: the interface went entirely English and the date stayed
 * « 18 août 2029 ». The currency stays carried by the amount; the LANGUAGE comes from the
 * reader.
 *
 * ⚠️ Read on every call and never memoised: a module that captures the language at import
 * freezes it for the session, and the language selector no longer changes anything -- the
 * sibling product paid exactly that price.
 */
/**
 * ⚠️ THE EM DASH IS FORBIDDEN IN ANY VISIBLE TEXT, the empty-value mark included. It
 * carried one, repeated in six places: « c'est la marque de l'IA ». A plain hyphen says the
 * same thing, and the sibling product already writes it that way.
 */
export const EMPTY = '-'

function activeLocale(): string {
  const lang = i18n.resolvedLanguage || i18n.language || 'fr'
  return lang.startsWith('en') ? 'en-GB' : 'fr-FR'
}

const MINOR_UNITS: Record<string, number> = {
  XOF: 0, XAF: 0, JPY: 0, KRW: 0, RWF: 0, UGX: 0, VND: 0, CLP: 0, ISK: 0,
}

export function minorUnits(currency: string): number {
  return MINOR_UNITS[(currency || '').toUpperCase()] ?? 2
}

/** An amount with its currency. `locale` follows the browser unless told otherwise. */
export function money(amount: number | string | null | undefined, currency: string): string {
  const value = typeof amount === 'string' ? Number(amount) : (amount ?? 0)
  if (!Number.isFinite(value)) return '-'
  const digits = minorUnits(currency)
  try {
    return new Intl.NumberFormat(activeLocale(), {
      style: 'currency',
      currency: (currency || 'EUR').toUpperCase(),
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    }).format(value)
  } catch {
    // An unknown ISO code must still print a readable amount rather than throw.
    return `${new Intl.NumberFormat(activeLocale(), { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value)} ${currency}`
  }
}

/** A plain number, no currency. For counts and multiples. */
export function number(value: number | string | null | undefined, digits = 2): string {
  const v = typeof value === 'string' ? Number(value) : (value ?? 0)
  if (!Number.isFinite(v)) return '-'
  return new Intl.NumberFormat(activeLocale(), { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(v)
}

/** A date as the user reads it. Empty rather than « Invalid Date ». */
export function day(value: string | null | undefined): string {
  if (!value) return '-'
  // 🔴 `new Date(value)` PARSED A STORED DAY AS UTC MIDNIGHT, and no `timeZone` option
  // below makes that zone-less -- omitting it uses the DEVICE's zone. Every date in the
  // product therefore slid back a day for a reader west of Greenwich. `dayOf` reads a
  // bare day as LOCAL midnight, after which no rendering can move it.
  const d = dayOf(value)
  if (Number.isNaN(d.getTime())) return '-'
  return new Intl.DateTimeFormat(activeLocale(), { day: '2-digit', month: 'short', year: 'numeric' }).format(d)
}

/** A percentage from a fraction (0.08 -> « 8 % »). */
export function percent(fraction: number | null | undefined, digits = 2): string {
  if (fraction === null || fraction === undefined || !Number.isFinite(fraction)) return '-'
  return `${number(fraction * 100, digits)} %`
}
