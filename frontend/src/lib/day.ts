/** Calendar days, told apart from instants.
 *
 * 🔴 THE RULE: a `Date` column is three numbers, not a point in time. It has no hour, so
 * no zone, so nothing to convert. Break that and the defect arrives in two mirrored
 * halves, both of which were live here:
 *
 *   * READING -- `new Date('2025-04-01')` is parsed as UTC by specification, so WEST of
 *     Greenwich it renders the day before. Reported from the screen in a sibling product:
 *     a lease starting on 1 April read as 31 March.
 *   * WRITING -- `toISOString().slice(0, 10)` reads a local moment back in UTC, so EAST
 *     of Greenwich, between midnight and the offset, it names YESTERDAY. Six screens here
 *     computed « today » that way.
 *
 * ⚠️ Neither is visible in Paris at noon, and that is where the pipeline and the people
 * writing this run. There is no amount of testing in the usual place that finds it.
 */

/** A calendar day from the server, read as that day. Instants pass through untouched. */
export function dayOf(value: string | Date): Date {
  if (value instanceof Date) return value
  const dayOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  if (dayOnly) return new Date(Number(dayOnly[1]), Number(dayOnly[2]) - 1, Number(dayOnly[3]))
  return new Date(value)
}

/** `yyyy-MM-dd` for a day, assembled from LOCAL parts.
 *
 * ⚠️ Never `toISOString()`, which is the very defect this replaces.
 */
export function isoDay(d: Date = new Date()): string {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

/** The reader's own today, as `yyyy-MM-dd`. */
export function todayIso(now: Date = new Date()): string {
  return isoDay(now)
}
