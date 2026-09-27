import { describe, expect, it } from 'vitest'
import login from './Login.tsx?raw'

/**
 * The product's own mark on the doors, never a letter in a square (the manager,
 * 27 Sept 2026: the new Comptoirs showed a « C » where the first ones show their logo).
 */
describe('the logo is on the doors', () => {
  it('the sign-in page shows the mark, not a letter standing in for it', () => {
    expect(login).toContain('<LogoMark')
    expect(login).not.toMatch(/font-bold">\s*C\s*<\/span>/)
  })
})
