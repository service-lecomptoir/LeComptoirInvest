import i18n from '@/i18n'

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
 * 🔴 LA LANGUE ACTIVE, PAS `fr-FR` EN DUR. La première version documentait longuement qu'il
 * ne faut JAMAIS supposer la devise… en codant la locale en dur trois lignes plus bas. Vu à
 * l'écran le 18 août : l'interface passait entièrement en anglais et la date restait
 * « 18 août 2029 ». La devise reste portée par le montant ; la LANGUE vient du lecteur.
 *
 * ⚠️ Lue à chaque appel et jamais mémorisée : un module qui capture la langue à l'import la
 * fige pour la session, et le sélecteur de langue ne change plus rien — le produit frère a
 * payé exactement cela.
 */
/**
 * ⚠️ LE TIRET CADRATIN EST INTERDIT DANS TOUT TEXTE VISIBLE, la marque de valeur vide
 * comprise. Elle en portait un, repete a six endroits : « c'est la marque de l'IA ». Un
 * trait d'union simple dit la meme chose, et le produit frere l'ecrit deja ainsi.
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
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '-'
  return new Intl.DateTimeFormat(activeLocale(), { day: '2-digit', month: 'short', year: 'numeric' }).format(d)
}

/** A percentage from a fraction (0.08 -> « 8 % »). */
export function percent(fraction: number | null | undefined, digits = 2): string {
  if (fraction === null || fraction === undefined || !Number.isFinite(fraction)) return '-'
  return `${number(fraction * 100, digits)} %`
}
