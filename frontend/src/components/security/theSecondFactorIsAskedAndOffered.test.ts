import { describe, expect, it } from 'vitest'

import en from '@/i18n/locales/en.json'
import fr from '@/i18n/locales/fr.json'
import API from '@/api/index.ts?raw'
import STORE from '@/store/authStore.ts?raw'
import SHELL from '@/components/layout/Shell.tsx?raw'
import LOGIN from '@/pages/Login.tsx?raw'
import SET_PASSWORD from '@/pages/SetPassword.tsx?raw'
import PROFILE from '@/pages/profile/MyProfile.tsx?raw'
import SECURITY from '@/pages/profile/SecuritySection.tsx?raw'

import BANNER from './TwoFactorBanner.tsx?raw'
import STEP from './TwoFactorStep.tsx?raw'

/**
 * The second factor (the owner, 2 Nov 2026): offered to every account in « Mon profil »,
 * recommended by a discreet banner to whoever runs the fund, asked after the password, and
 * after a password link, which proves the mailbox and not the phone.
 */
describe('the second factor', () => {
  it('is asked after the password, with a backup code and a way back', () => {
    expect(STORE).toContain('if (data.two_factor_required && data.two_factor_token) return { twoFactorToken: data.two_factor_token }')
    expect(API).toContain("'/auth/login/two-factor'")
    expect(LOGIN).toContain('<TwoFactorStep')
    expect(STEP).toContain("t('twoFactor.useBackup')")
    expect(STEP).toContain("t('twoFactor.backToPassword')")
    expect(STEP).toContain('autoComplete="one-time-code"')
  })

  it('is asked after a password link too, never skipped', () => {
    expect(SET_PASSWORD).toContain('data.two_factor_required && data.two_factor_token')
    expect(SET_PASSWORD).toContain("navigate('/login', { replace: true, state: { twoFactorToken: data.two_factor_token } })")
    expect(LOGIN).toContain('handed.twoFactorToken')
  })

  it('is offered in the profile, codes shown once, removal with the password and a code', () => {
    expect(PROFILE).toContain('<SecuritySection />')
    expect(SECURITY).toContain('<img')
    expect(SECURITY).toContain("t('twoFactor.kept')")
    expect(SECURITY).toContain("a.download = 'backup-codes.txt'")
    // The password AND a code, each checked under its field before anything leaves.
    expect(SECURITY).toContain("{ name: 'password', value: password, required: true }")
    expect(SECURITY).toContain("{ name: 'code', value: code, required: true }")
    expect(SECURITY).toContain('sm:grid-cols-2')
    expect(SECURITY).not.toMatch(/window\.(confirm|alert|prompt)/)
  })

  it('is recommended by a banner the server decides, silenced for a month', () => {
    expect(SHELL).toContain('<TwoFactorBanner />')
    expect(BANNER).toContain('data.recommended && !data.enabled')
    expect(BANNER).toContain('30 * 24 * 3600 * 1000')
    expect(BANNER).toContain("t('twoFactor.bannerDismiss')")
  })

  it('speaks both languages, with the screens the owner named', () => {
    expect(fr.twoFactor.useBackup).toBe('Utiliser un code de secours')
    expect(fr.twoFactor.backToPassword).toBe('Revenir au mot de passe')
    expect(fr.twoFactor.kept).toBe("J'ai mis ces codes en lieu sûr.")
    expect(fr.twoFactor.bannerText).toBe('Protégez votre compte : activez la double authentification.')
    expect(fr.twoFactor.bannerDismiss).toBe('Plus tard')
    expect(Object.keys(en.twoFactor).sort()).toEqual(Object.keys(fr.twoFactor).sort())
  })
})
