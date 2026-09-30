import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { KeyRound } from 'lucide-react'

import { authApi } from '@/api'
import { errorMessage } from '@/api/client'
import { LanguageSwitcher } from '@/components/common/LanguageSwitcher'
import { LogoMark } from '@/components/common/Logo'
import { Notice } from '@/components/common/Primitives'
import { Button, Input, Spinner } from '@/components/ui'
import { useAuthStore } from '@/store/authStore'
import { toast } from '@/store/toast'

/**
 * The page a password link opens: the holder CHOOSES their password, then is signed in.
 *
 * 🔴 NO PASSWORD TRAVELS BY E-MAIL (customer recipe, 30 Sept 2026: a new account received a
 * temporary one in clear, and a forgotten password had no way back at all). The letter
 * carries a link here, for a first password (a week) as for a forgotten one (two hours).
 *
 * ⚠️ THE LINK IS CHECKED BEFORE ANYTHING IS TYPED: a dead link says so at once, with the way
 * to a new one, rather than after the person has typed their password twice.
 */
export default function SetPassword() {
  const { t, i18n } = useTranslation()
  const { token = '' } = useParams()
  const navigate = useNavigate()
  const adopt = useAuthStore((s) => s.adopt)
  const [link, setLink] = useState<{ email: string; purpose: 'welcome' | 'reset' } | null>(null)
  const [dead, setDead] = useState<string | null>(null)
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const title = link?.purpose === 'welcome' ? t('setPassword.welcomeTitle') : t('setPassword.resetTitle')

  useEffect(() => {
    document.title = `Le Comptoir Invest | ${title}`
  }, [title, i18n.language])

  useEffect(() => {
    authApi
      .passwordLink(token)
      .then(({ data }) => setLink(data))
      .catch((err) => setDead(errorMessage(err)))
  }, [token])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (password !== confirm) {
      setError(t('password.mismatch'))
      return
    }
    if (password.length < 10) {
      setError(t('password.tooShort'))
      return
    }
    setBusy(true)
    try {
      const { data } = await authApi.setPasswordThroughLink(token, password)
      await adopt(data.access_token)
      toast.success(t('setPassword.done'))
      navigate('/', { replace: true })
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen bg-white flex items-start justify-center p-6">
      <div className="w-full max-w-sm">
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-2.5">
            <LogoMark size={32} className="shrink-0 rounded-md" />
            <span className="text-base font-semibold text-brand-navy tracking-tight">
              {t('brand.name')}
            </span>
          </div>
          <LanguageSwitcher />
        </div>

        {dead ? (
          <div className="space-y-4">
            <Notice tone="bad" title={t('setPassword.deadTitle')}>
              {dead}
            </Notice>
            <Link to="/login" className="inline-block text-sm text-brand-navy underline">
              {t('setPassword.askNew')}
            </Link>
          </div>
        ) : !link ? (
          <p className="flex items-center gap-2 text-sm text-gray-500">
            <Spinner /> {t('setPassword.checking')}
          </p>
        ) : (
          <form onSubmit={submit} noValidate>
            <h1 className="text-xl font-semibold text-gray-900 tracking-tight">{title}</h1>
            <p className="mt-1 mb-6 text-sm text-gray-500 break-words">
              {t('setPassword.for', { email: link.email })}
            </p>
            <div className="space-y-4">
              <Input
                label={t('password.new')}
                hint={t('password.newHint')}
                type="password"
                revealable
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
              <Input
                label={t('password.confirm')}
                hint={t('password.confirmHint')}
                type="password"
                revealable
                autoComplete="new-password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                required
              />
            </div>
            {error && (
              <p className="mt-4 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                {error}
              </p>
            )}
            <Button type="submit" fullWidth isLoading={busy} className="mt-6">
              <KeyRound size={15} /> {t('setPassword.submit')}
            </Button>
          </form>
        )}
      </div>
    </div>
  )
}
