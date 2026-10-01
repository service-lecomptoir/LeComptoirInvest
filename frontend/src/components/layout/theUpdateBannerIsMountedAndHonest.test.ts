/**
 * The update banner is MOUNTED, and its probe cannot lie from a cache.
 *
 * Ported from Le Comptoir Immo, where the component was born from a real exchange (4 Sept):
 * a fix WAS deployed while a long-lived tab kept running the old bundle, and the reader
 * reported the fix as not deployed although production was current. A banner that exists
 * but is not mounted in the signed-in layout would repeat the oldest shape of the house:
 * what LOOKS done.
 */

import { describe, expect, it } from 'vitest'

import BANNER from './UpdateBanner.tsx?raw'
import SHELL from './Shell.tsx?raw'
import fr from '../../i18n/locales/fr.json'
import en from '../../i18n/locales/en.json'

describe('the update banner', () => {
  it('is mounted once, in the signed-in layout', () => {
    expect(SHELL).toContain("import { UpdateBanner } from '@/components/layout/UpdateBanner'")
    expect(SHELL.split('<UpdateBanner />').length - 1).toBe(1)
  })

  it('probes the server without a cache in the way', () => {
    // A cached index.html would compare the old bundle with itself, forever.
    expect(BANNER).toContain("cache: 'no-store'")
    expect(BANNER).toContain('update-probe=')
  })

  it('offers the one gesture in every language', () => {
    for (const cat of [fr, en] as Array<Record<string, any>>) {
      expect(cat.updateBanner?.newVersion, 'newVersion key').toBeTruthy()
      expect(cat.updateBanner?.reload, 'reload key').toBeTruthy()
    }
  })
})
