/**
 * 🔴 THE LANGUAGES BEHIND ONE BUTTON, ON EVERY SCREEN (the owner, 28 Nov 2026, after Le Comptoir
 * Immo's: the flags as a list, in every Le Comptoir tool). The segmented control, one button
 * per language side by side, is gone: every picker is `LanguageMenu`, the flag and the code
 * of the current language, the list on a click. The layout is measured in a browser at
 * 1 440, 375 and 320 px; this holds the markup.
 */
import { describe, expect, it } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

const SRC = join(__dirname, '..', '..')
const read = (rel: string) => readFileSync(join(SRC, rel), 'utf8')

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) return walk(full)
    return /\.tsx$/.test(entry) && !/\.test\.tsx$/.test(entry) ? [full] : []
  })
}

/** Every screen that offers the language, and the side its list opens to: `right` for a
 *  button at the right end of a bar, where a list opened to the right runs off the screen. */
const SCREENS: Record<string, string> = {
  'components/layout/Shell.tsx': '<LanguageMenu withCode align="right" />',
  'pages/Login.tsx': '<LanguageMenu withCode align="right" />',
  'pages/SetPassword.tsx': '<LanguageMenu withCode align="right" />',
  'pages/Privacy.tsx': '<LanguageMenu withCode align="right" />',
  'pages/Pricing.tsx': '<LanguageMenu withCode align="right" />',
  'pages/Landing.tsx': '<LanguageMenu withCode />',
}

describe('the language picker', () => {
  it('is one button everywhere: the buttons side by side are gone', () => {
    const files = walk(SRC)
    expect(files.length).toBeGreaterThan(30)
    const sideBySide = files.filter((f) => /<LanguageSwitcher\b/.test(readFileSync(f, 'utf8')))
    expect(sideBySide).toEqual([])
    expect(read('components/common/LanguageSwitcher.tsx')).not.toMatch(/export function LanguageSwitcher\b/)
  })

  it('is the folded button on every screen that offers the language', () => {
    for (const [screen, picker] of Object.entries(SCREENS)) expect(read(screen), screen).toContain(picker)
  })

  it('says the current language by its flag and its code, and lists the languages by their name', () => {
    const picker = read('components/common/LanguageSwitcher.tsx')
    expect(picker).toContain('aria-haspopup="menu"')
    expect(picker).toContain('{withCode && <span>{current.slice(0, 2)}</span>}')
    expect(picker).toContain('role="menuitemradio"')
    expect(picker).toContain("align === 'right' ? 'right-0' : 'left-0'")
  })
})
