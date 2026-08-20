/**
 * Ce qui distingue une traduction d'une recopie. UNE seule fois.
 *
 * 🔴 CETTE RÈGLE VIVAIT EN DEUX EXEMPLAIRES : dans `scripts/i18n-check.mjs`, que la CI
 * lance, et dans `src/i18n/catalogue.test.ts`, que vitest lance. Elles n'avaient jamais
 * divergé, et c'est exactement pourquoi il fallait les réunir avant qu'elles le fassent :
 * corriger l'une laisse l'autre rouge, et la première chose qu'on fait devant une garde
 * rouge qu'on croit avoir corrigée, c'est douter de la garde.
 *
 * Le symptôme a été mesuré : ajouter `brand.full` a fait tomber les deux, l'une après
 * l'autre.
 */

/** Trois mots, c'est là qu'une phrase commence.
 *
 *  ⚠️ LE CRITÈRE EST LE NOMBRE DE MOTS, PAS LA LONGUEUR. « Distributions » fait treize
 *  caractères et s'écrit pareil dans les deux langues ; un seuil sur la longueur l'aurait
 *  signalé et aurait appris à celui qui le rencontre à élargir la liste d'exceptions
 *  jusqu'à ce que la garde ne veuille plus rien dire. Deux langues d'accord sur une PHRASE
 *  ENTIÈRE, voilà ce qui prouve une recopie.
 */
const MIN_WORDS = 3

/**
 * 🔴 UN NOM DE MARQUE NE SE TRADUIT PAS, et c'est tout ce que `brand.` contient.
 * « Le Comptoir Invest » fait trois mots et s'écrit pareil des deux côtés : le critère
 * y voit une recopie, alors qu'une marque traduite serait le défaut.
 *
 * ⚠️ L'EXEMPTION PORTE SUR UN ESPACE DE NOMS, JAMAIS SUR UNE LISTE DE CLÉS. Une liste de
 * clés grandit d'une ligne chaque fois que quelqu'un est pressé. Un espace de noms, lui, se
 * défend : ce qui vit sous `brand.` est un nom propre, ou n'a rien à y faire.
 */
const NEVER_TRANSLATED = 'brand.'

/** Les clés dont la version anglaise est, selon toute vraisemblance, le français recopié. */
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
