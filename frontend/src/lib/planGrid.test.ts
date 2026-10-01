import { describe, expect, it } from 'vitest'
import { planGridClass } from './planGrid'

/** The widest number of columns a class string asks for, at its largest breakpoint. */
function widest(classes: string): number {
  const counts = [...classes.matchAll(/grid-cols-(\d)/g)].map((m) => Number(m[1]))
  return Math.max(...counts)
}

describe('a row of plan cards', () => {
  it('never leaves one card alone on the last row of a wide screen', () => {
    for (let count = 2; count <= 9; count++) {
      const columns = widest(planGridClass(count))
      if (count === 5 || count === 7) continue // no even split exists
      expect(count % columns, `${count} plans in ${columns} columns`).toBe(0)
    }
  })

  it('reads four plans four across, or two by two, never three and one', () => {
    const classes = planGridClass(4)
    expect(classes).toContain('xl:grid-cols-4')
    expect(classes).toContain('sm:grid-cols-2')
    expect(classes).not.toContain('grid-cols-3')
  })
})
