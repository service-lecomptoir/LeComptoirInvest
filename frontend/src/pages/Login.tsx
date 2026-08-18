import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Button, Input } from '@/components/ui'
import { LanguageSwitcher } from '@/components/common/LanguageSwitcher'
import { errorMessage } from '@/api/client'
import { useAuthStore } from '@/store/authStore'

export default function Login() {
  const { t } = useTranslation()
  const { login, isAuthenticated } = useAuthStore()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (isAuthenticated) return <Navigate to="/" replace />

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await login(email.trim(), password)
      navigate('/', { replace: true })
    } catch (err) {
      // Shown in place rather than as a toast: the user is looking at this form, and a
      // message that fades while they retype is a message they will miss.
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen grid lg:grid-cols-2">
      {/* The left panel is the only decorative surface in the product. Every other screen
          is a table: a fund console earns trust by being legible, not by being styled. */}
      <div className="hidden lg:flex flex-col justify-between bg-brand-navy p-10 text-white">
        <div className="flex items-center gap-2.5">
          <span className="grid place-items-center w-8 h-8 rounded-md bg-brand-teal text-white text-sm font-bold">
            C
          </span>
          <span className="text-base font-semibold tracking-tight">
            {t('brand.first')} <span className="text-brand-teal">{t('brand.second')}</span>
          </span>
        </div>
        <div className="max-w-md">
          <p className="text-2xl font-semibold leading-snug tracking-tight">{t('login.pitchTitle')}</p>
          <p className="mt-4 text-sm text-white/70 leading-relaxed">{t('login.pitchBody')}</p>
        </div>
        <p className="text-xs text-white/40">Le Comptoir</p>
      </div>

      <div className="flex items-center justify-center p-6 bg-white">
        <form onSubmit={submit} className="w-full max-w-sm">
          <div className="flex items-center justify-between mb-8">
            <div className="lg:hidden flex items-center gap-2.5">
              <span className="grid place-items-center w-8 h-8 rounded-md bg-brand-navy text-white text-sm font-bold">
                C
              </span>
              <span className="text-base font-semibold text-brand-navy tracking-tight">
                {t('brand.name')}
              </span>
            </div>
            {/* The picker is on the sign-in page on purpose: somebody who cannot read the
                form is exactly the person who needs to change the language. */}
            <div className="ml-auto">
              <LanguageSwitcher />
            </div>
          </div>

          <h1 className="text-xl font-semibold text-gray-900 tracking-tight">{t('login.title')}</h1>
          <p className="mt-1 mb-6 text-sm text-gray-500">{t('login.subtitle')}</p>

          <div className="space-y-4">
            <Input
              label={t('login.email')}
              type="email"
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
            <Input
              label={t('login.password')}
              type="password"
              revealable
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          {error && (
            <p className="mt-4 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {error}
            </p>
          )}

          <Button type="submit" fullWidth isLoading={busy} className="mt-6">
            {t('login.submit')}
          </Button>
        </form>
      </div>
    </div>
  )
}
