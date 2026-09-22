/**
 * What tells a translation from a copy. ONE single time.
 *
 * 🔴 THIS RULE LIVED IN TWO COPIES: in `scripts/i18n-check.mjs`, which CI runs, and in
 * `src/i18n/catalogue.test.ts`, which vitest runs. They had never diverged, and that is
 * exactly why they had to be brought together before they did: fixing one leaves the other
 * red, and the first thing one does in front of a red guard one believes to have fixed is
 * to doubt the guard.
 *
 * The symptom was measured: adding `brand.full` brought both down, one after the other.
 */

/** Three words, that is where a sentence begins.
 *
 *  ⚠️ THE CRITERION IS THE NUMBER OF WORDS, NOT THE LENGTH. « Distributions » is thirteen
 *  characters long and is written the same way in both languages; a threshold on the
 *  length would have flagged it and would have taught whoever meets it to widen the
 *  exception list until the guard no longer meant anything. Two languages agreeing on a
 *  WHOLE SENTENCE, that is what proves a copy.
 */
const MIN_WORDS = 3

/**
 * 🔴 A BRAND NAME IS NOT TRANSLATED, and that is all `brand.` contains.
 * « Le Comptoir Invest » is three words and is written the same way on both sides: the
 * criterion sees a copy there, whereas a translated brand would be the defect.
 *
 * ⚠️ THE EXEMPTION BEARS ON A NAMESPACE, NEVER ON A LIST OF KEYS. A list of keys grows by
 * one line every time somebody is in a hurry. A namespace, on the other hand, defends
 * itself: what lives under `brand.` is a proper name, or has nothing to do there.
 */
const NEVER_TRANSLATED = 'brand.'

/** The keys whose English version is, in all likelihood, the French copied over. */
export function copiedKeys(
  fr: Record<string, unknown>,
  en: Record<string, unknown>,
): string[] {
  return Object.keys(fr).filter(
    (key) =>
      key in en &&
      fr[key] === en[key] &&
      String(fr[key]).trim().split(/\s+/).length >= MIN_WORDS &&
      !key.startsWith(NEVER_TRANSLATED),
  )
}
