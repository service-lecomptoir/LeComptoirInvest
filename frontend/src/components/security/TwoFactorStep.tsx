import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ShieldCheck } from 'lucide-react'
import { Button, Input } from '@/components/ui'
import { useFieldCheck } from '@/lib/formCheck'
import { useAuthStore } from '@/store/authStore'

/**
 * The second step of the sign-in (3 Nov 2026): the code of the authenticator app, or one
 * backup code (« Utiliser un code de secours »). Shown after the password when the
 * account's second factor is on, and after a password link, which proves the mailbox and
 * not the phone.
 *
 * `refusal` turns a failure into the sentence to show: the sign-in page's own, which
 * keeps the server's words and says « unreachable » or « too many attempts » by case.
 */
export function TwoFactorStep({
  twoFactorToken,
  onSignedIn,
  onCancel,
  refusal,
}: {
  twoFactorToken: string
  onSignedIn: () => void
  onCancel: () => void
  refusal: (err: unknown) => string
}) {
  const { t } = useTranslation()
  const loginTwoFactor = useAuthStore((s) => s.loginTwoFactor)
  const [code, setCode] = useState('')
  const [useBackup, setUseBackup] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const { errors, check } = useFieldCheck()

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!check([{ name: 'code', value: code, required: true }])) return
    setBusy(true)
    try {
      await loginTwoFactor(twoFactorToken, useBackup ? { backup_code: code.trim() } : { code: code.trim() })
      onSignedIn()
    } catch (err) {
      setError(refusal(err))
      setCode('')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} noValidate>
      <h1 className="text-xl font-semibold text-gray-900 tracking-tight">{t('twoFactor.loginTitle')}</h1>
      <p className="mb-6 mt-1 flex items-start gap-2 text-sm text-gray-500">
        <ShieldCheck size={16} className="mt-0.5 shrink-0 text-brand-navy" />
        <span>{useBackup ? t('twoFactor.loginIntroBackup') : t('twoFactor.loginIntro')}</span>
      </p>
      <Input
        label={useBackup ? t('twoFactor.backupCodeLabel') : t('twoFactor.loginCodeLabel')}
        hint={useBackup ? t('twoFactor.backupCodeHelp') : t('twoFactor.loginCodeHelp')}
        value={code}
        onChange={(e) => setCode(e.target.value)}
        inputMode={useBackup ? 'text' : 'numeric'}
        autoComplete="one-time-code"
        autoFocus
        maxLength={useBackup ? 20 : 7}
        placeholder={useBackup ? 'abcde-23456' : '123456'}
        className="tracking-widest"
        required
        error={errors.code}
      />
      {error && (
        <p role="alert" className="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </p>
      )}
      <Button type="submit" fullWidth isLoading={busy} className="mt-6">
        {t('twoFactor.loginSubmit')}
      </Button>
      <div className="mt-4 flex flex-col gap-2 text-sm sm:flex-row sm:justify-between">
        <button
          type="button"
          onClick={() => {
            setUseBackup((v) => !v)
            setCode('')
            setError(null)
          }}
          className="text-left font-medium text-brand-navy hover:underline"
        >
          {useBackup ? t('twoFactor.useApp') : t('twoFactor.useBackup')}
        </button>
        <button type="button" onClick={onCancel} className="text-left text-gray-500 hover:text-brand-navy">
          {t('twoFactor.backToPassword')}
        </button>
      </div>
    </form>
  )
}
