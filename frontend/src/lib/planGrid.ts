/**
 * The columns of a row of plan cards, chosen from the NUMBER of cards so that the last row
 * never holds a lone card: four plans read four across on a wide screen and two by two on
 * a narrower one, never three and then one alone under them (the manager, 1 Oct 2026, on a
 * pricing page where « Sur devis » sat by itself on a second row at 1360 px).
 *
 * ⚠️ WRITTEN THE SAME IN EVERY PRODUCT OF THE HOUSE (Immo, PDF, Compta, BTP, Syndic, Invest,
 * Séjour, Market): one rule, one layout. The class names are literal so that Tailwind
 * finds them in the source.
 */
export function planGridClass(count: number): string {
  if (count <= 1) return 'grid-cols-1 max-w-sm mx-auto'
  if (count === 2) return 'grid-cols-1 sm:grid-cols-2 max-w-3xl mx-auto'
  if (count % 4 === 0) return 'grid-cols-1 sm:grid-cols-2 xl:grid-cols-4'
  if (count % 3 === 0) return 'grid-cols-1 md:grid-cols-3'
  if (count % 2 === 0) return 'grid-cols-1 sm:grid-cols-2'
  // Five or seven: three across leaves two or one beside a full row; the least bad.
  return 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3'
}
