/**
 * What the sign-up screen says after sending, read from the server's word.
 *
 * 🔴 A SUCCESS TONE ONLY FOR WHAT SUCCEEDED. The console may file a sign-up whose
 * confirmation e-mail could not leave (`confirmation_not_sent`), and the server may give
 * up waiting for an answer that was perhaps given (`not_answered`): showing either in
 * green under « Vérifiez votre boîte e-mail » sends the prospect waiting for a letter that
 * is not coming (customer recipe, 30 Sept 2026: « Demande enregistrée » in green over
 * « l'e-mail de confirmation n'a pas pu partir »). Showing either in the red error box
 * says « refused » of a request that was probably filed. Both are warnings, with a way
 * forward.
 */

export type OutcomeTone = 'success' | 'warning'

/** The words that did not go all the way: an account already there, an e-mail that
 *  did not leave, an answer that did not come. */
const WARNINGS = new Set(['account_exists', 'confirmation_not_sent', 'not_answered'])

/** The words after which trying again is the next step. */
const RETRY = new Set(['confirmation_not_sent', 'not_answered'])

/** The words the screen has a title for; any other one reads as « Demande enregistrée ». */
export const KNOWN_OUTCOMES = [
  'confirmation_sent',
  'confirmation_not_sent',
  'not_answered',
  'account_created',
  'account_exists',
  'received',
] as const

export function outcomeTone(status: string): OutcomeTone {
  return WARNINGS.has(status) ? 'warning' : 'success'
}

export function offersRetry(status: string): boolean {
  return RETRY.has(status)
}

export function outcomeTitleKey(status: string): string {
  const known = (KNOWN_OUTCOMES as readonly string[]).includes(status)
  return `signup.outcomes.${known ? status : 'received'}`
}
