import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Check, Copy, Download, KeyRound, QrCode, ShieldCheck, ShieldOff } from 'lucide-react'
import { authApi } from '@/api'
import { errorMessage } from '@/api/client'
import { Button, Input } from '@/components/ui'
import { Card } from '@/components/common/Primitives'
import { InfoBubble } from '@/components/common/InfoBubble'
import { useFieldCheck } from '@/lib/formCheck'
import { toast } from '@/store/toast'
import type { TwoFactorSetup, TwoFactorStatus } from '@/types'

/** The secret in groups of four, easier to type into an app by hand. */
const grouped = (secret: string) => secret.replace(/(.{4})/g, '$1 ').trim()

/**
 * The ten backup codes, shown ONCE (the server keeps their fingerprints only): copy, save
 * as a text file, and « J'ai mis ces codes en lieu sûr » before the box closes on them.
 */
export function BackupCodesList({ codes, onDone }: { codes: string[]; onDone: () => void }) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)
  const [kept, setKept] = useState(false)
  const text = codes.join('\n')

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
    } catch {
      setCopied(false)
    }
  }

  const download = () => {
    const blob = new Blob([`${t('twoFactor.fileHeader')}\n\n${text}\n`], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'backup-codes.txt'
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-3 rounded-xl border border-sky-200 bg-sky-50/50 p-4">
      <div className="flex items-center gap-1.5">
        <h3 className="text-sm font-semibold text-gray-900">{t('twoFactor.backupTitle')}</h3>
        <InfoBubble text={t('twoFactor.backupInfo')} label={t('twoFactor.backupTitle')} />
      </div>
      <ul className="grid grid-cols-1 gap-2 font-mono text-sm sm:grid-cols-2">
        {codes.map((c) => (
          <li key={c} className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-center text-gray-800">
            {c}
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="secondary" size="sm" onClick={copy}>
          {copied ? <Check size={14} className="text-emerald-600" /> : <Copy size={14} />}
          {copied ? t('twoFactor.copied') : t('twoFactor.copy')}
        </Button>
        <Button type="button" variant="secondary" size="sm" onClick={download}>
          <Download size={14} /> {t('twoFactor.download')}
        </Button>
      </div>
      <div>
        <label htmlFor="two-factor-kept" className="flex cursor-pointer items-start gap-2 text-sm text-gray-800">
          <input
            id="two-factor-kept"
            type="checkbox"
            checked={kept}
            onChange={(event) => setKept(event.target.checked)}
            aria-describedby="two-factor-kept-help"
            className="mt-0.5 h-4 w-4 shrink-0 accent-brand-navy"
          />
          <span>{t('twoFactor.kept')}</span>
        </label>
        <p id="two-factor-kept-help" className="mt-1 ml-6 text-xs text-gray-500">{t('twoFactor.keptHelp')}</p>
      </div>
      <div className="flex justify-end">
        <Button type="button" disabled={!kept} onClick={onDone}>
          {t('twoFactor.done')}
        </Button>
      </div>
    </div>
  )
}

type Action = 'codes' | 'disable'

/**
 * « Sécurité » of « Mon profil » (the owner, 2 Nov 2026): the second factor of the
 * signed-in account. Set it up (QR code and key shown once, a first code, ten backup codes
 * shown once), draw new backup codes, switch it off; the last two ask the password AND a
 * code. Offered to every account, recommended to whoever runs the fund.
 */
export function SecuritySection() {
  const { t } = useTranslation()
  const [status, setStatus] = useState<TwoFactorStatus | null>(null)
  const [setup, setSetup] = useState<TwoFactorSetup | null>(null)
  const [firstCode, setFirstCode] = useState('')
  const [codes, setCodes] = useState<string[] | null>(null)
  const [action, setAction] = useState<Action | null>(null)
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [useBackup, setUseBackup] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { errors, check } = useFieldCheck()

  const load = useCallback(() => {
    authApi.twoFactor
      .status()
      .then(({ data }) => setStatus(data))
      .catch(() => setStatus(null))
  }, [])
  useEffect(() => {
    load()
  }, [load])
  // Opened from the banner (« /profile#security »): the section is brought into view.
  useEffect(() => {
    if (status && window.location.hash === '#security') {
      document.getElementById('security')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [status])

  const resetForm = () => {
    setPassword('')
    setCode('')
    setUseBackup(false)
    setError(null)
  }

  const start = async () => {
    setError(null)
    setBusy(true)
    try {
      const { data } = await authApi.twoFactor.setup()
      setSetup(data)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const activate = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!check([{ name: 'firstCode', value: firstCode, required: true, minLength: 6 }])) return
    setBusy(true)
    try {
      const { data } = await authApi.twoFactor.activate(firstCode.trim())
      setCodes(data.backup_codes)
      setSetup(null)
      setFirstCode('')
      toast.success(t('twoFactor.enabledToast'))
      load()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const confirm = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    const fine = check([
      { name: 'password', value: password, required: true },
      { name: 'code', value: code, required: true },
    ])
    if (!fine) return
    setBusy(true)
    const proof = useBackup ? { backup_code: code.trim() } : { code: code.trim() }
    try {
      if (action === 'codes') {
        const { data } = await authApi.twoFactor.backupCodes(password, proof)
        setCodes(data.backup_codes)
      } else {
        await authApi.twoFactor.disable(password, proof)
        toast.success(t('twoFactor.disabledToast'))
      }
      setAction(null)
      resetForm()
      load()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const enabled = !!status?.enabled
  const left = status?.backup_codes_remaining ?? 0

  return (
    <section id="security" className="max-w-xl scroll-mt-20">
      <div className="mb-3 flex items-center gap-1.5">
        <h2 className="text-sm font-semibold text-gray-900">{t('twoFactor.securityTitle')}</h2>
        <InfoBubble text={t('twoFactor.info')} label={t('twoFactor.title')} />
      </div>
      <Card className="space-y-4 p-5">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="rounded-lg border border-gray-100 bg-gray-50 px-4 py-3">
            <p className="text-xs text-gray-500">{t('twoFactor.title')}</p>
            <p className={`text-sm font-semibold ${enabled ? 'text-emerald-700' : 'text-gray-700'}`}>
              {status ? (enabled ? t('twoFactor.statusOn') : t('twoFactor.statusOff')) : '…'}
            </p>
            {status && !enabled && status.recommended && (
              <p className="mt-0.5 text-xs text-amber-700">{t('twoFactor.recommended')}</p>
            )}
          </div>
          {enabled && (
            <div className="rounded-lg border border-gray-100 bg-gray-50 px-4 py-3">
              <p className="text-xs text-gray-500">{t('twoFactor.backupLeft')}</p>
              <p className={`text-sm font-semibold ${left <= 3 ? 'text-amber-700' : 'text-gray-800'}`}>
                {t('twoFactor.backupLeftValue', { count: left })}
              </p>
            </div>
          )}
        </div>

        {error && (
          <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </p>
        )}

        {codes && <BackupCodesList codes={codes} onDone={() => setCodes(null)} />}

        {/* ── Not on: the set-up ── */}
        {!codes && status && !enabled && !setup && (
          <div className="space-y-3">
            <p className="text-sm text-gray-600">{t('twoFactor.intro')}</p>
            <Button type="button" onClick={start} isLoading={busy} leftIcon={<QrCode size={15} />}>
              {t('twoFactor.start')}
            </Button>
          </div>
        )}
        {!codes && setup && (
          <form onSubmit={activate} noValidate className="space-y-4">
            <div className="flex flex-col items-center gap-4 sm:flex-row sm:items-start">
              <img
                src={setup.qr_code}
                alt={t('twoFactor.qrAlt')}
                className="h-44 w-44 rounded-lg border border-gray-200 bg-white"
              />
              <div className="w-full min-w-0 space-y-1">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-medium text-gray-600">{t('twoFactor.secretLabel')}</span>
                  <InfoBubble text={t('twoFactor.secretInfo')} label={t('twoFactor.secretLabel')} />
                </div>
                <p className="break-all rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 font-mono text-sm text-gray-800">
                  {grouped(setup.secret)}
                </p>
              </div>
            </div>
            <Input
              label={t('twoFactor.codeLabel')}
              hint={t('twoFactor.codeHelp')}
              value={firstCode}
              onChange={(e) => setFirstCode(e.target.value)}
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={7}
              placeholder="123456"
              required
              error={errors.firstCode}
            />
            <div className="flex justify-end">
              <Button
                type="submit"
                isLoading={busy}
                leftIcon={<ShieldCheck size={15} />}
              >
                {t('twoFactor.activate')}
              </Button>
            </div>
          </form>
        )}

        {/* ── On: new codes, switch off ── */}
        {!codes && enabled && !action && (
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="secondary"
              size="sm"
              leftIcon={<KeyRound size={14} />}
              onClick={() => {
                resetForm()
                setAction('codes')
              }}
            >
              {t('twoFactor.newCodes')}
            </Button>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              className="text-red-700"
              leftIcon={<ShieldOff size={14} />}
              onClick={() => {
                resetForm()
                setAction('disable')
              }}
            >
              {t('twoFactor.disable')}
            </Button>
          </div>
        )}
        {!codes && enabled && action && (
          <form onSubmit={confirm} noValidate className="space-y-3 border-t border-gray-100 pt-4">
            <div className="flex items-center gap-1.5">
              <h3 className="text-sm font-semibold text-gray-900">
                {action === 'codes' ? t('twoFactor.newCodes') : t('twoFactor.disable')}
              </h3>
              <InfoBubble
                text={action === 'codes' ? t('twoFactor.newCodesInfo') : t('twoFactor.disableInfo')}
                label={action === 'codes' ? t('twoFactor.newCodes') : t('twoFactor.disable')}
              />
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Input
                label={t('twoFactor.passwordLabel')}
                hint={t('twoFactor.passwordHelp')}
                type="password"
                revealable
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
                error={errors.password}
              />
              <Input
                label={useBackup ? t('twoFactor.backupCodeLabel') : t('twoFactor.codeLabel')}
                hint={useBackup ? t('twoFactor.backupCodeHelp') : t('twoFactor.codeNowHelp')}
                value={code}
                onChange={(e) => setCode(e.target.value)}
                inputMode={useBackup ? 'text' : 'numeric'}
                autoComplete="one-time-code"
                required
                error={errors.code}
              />
            </div>
            <button
              type="button"
              onClick={() => {
                setUseBackup((v) => !v)
                setCode('')
              }}
              className="text-xs font-medium text-brand-navy hover:underline"
            >
              {useBackup ? t('twoFactor.useApp') : t('twoFactor.useBackup')}
            </button>
            <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  setAction(null)
                  resetForm()
                }}
              >
                {t('common.cancel')}
              </Button>
              <Button
                type="submit"
                variant={action === 'disable' ? 'danger' : 'primary'}
                isLoading={busy}
              >
                {t('twoFactor.confirm')}
              </Button>
            </div>
          </form>
        )}
      </Card>
    </section>
  )
}
