import { useEffect, useState } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Button, Input } from '@/components/ui'
import { Notice } from '@/components/common/Primitives'
import { LanguageSwitcher } from '@/components/common/LanguageSwitcher'
import { authApi } from '@/api'
import { errorMessage } from '@/api/client'
import { useAuthStore } from '@/store/authStore'
import { LogoMark } from '@/components/common/Logo'
import { SignupForm } from '@/components/signup/SignupForm'
import { safeNext } from '@/lib/nextPath'

export default function Login() {
  const { t, i18n } = useTranslation()

  // ⚠️ SIGN-IN IS OUTSIDE THE SHELL, therefore outside the effect that names the tabs. It
  // is however the only screen a reader sees BEFORE having an account open, and often the
  // one they leave in a tab while looking for their password elsewhere.
  useEffect(() => {
    document.title = `Le Comptoir Invest | ${t('login.title')}`
  }, [t, i18n.language])
  const { login, isAuthenticated } = useAuthStore()
  const navigate = useNavigate()
  // Where the reader was sent away from, if it is a path of this site (`lib/nextPath`).
  const [params] = useSearchParams()
  const next = safeNext(params.get('next')) ?? '/'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  // 🔴 THE SIGN-UP GOES THROUGH THE CONSOLE (`SignupForm`), as on Le Comptoir RH: the
  // prospect chooses a catalogue plan, Alice confirms the e-mail and opens the account.
  const [signingUp, setSigningUp] = useState(false)
  // 🔴 A FORGOTTEN PASSWORD HAS A WAY BACK (customer recipe, 30 Sept 2026: there was none,
  // and the only exit was writing to support). A link by e-mail, never a password.
  const [forgetting, setForgetting] = useState(false)

  if (isAuthenticated) return <Navigate to={next} replace />

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!email.trim() || !password) {
      setError(t('login.missing'))
      return
    }
    setBusy(true)
    try {
      await login(email.trim(), password)
      navigate(next, { replace: true })
    } catch (err) {
      // Shown in place rather than as a toast: the user is looking at this form, and a
      // message that fades while they retype is a message they will miss.
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen grid grid-cols-1 lg:grid-cols-2">
      {/* The left panel is the only decorative surface in the product. Every other screen
          is a table: a fund console earns trust by being legible, not by being styled. */}
      <div className="hidden lg:flex flex-col justify-between bg-brand-navy p-10 text-white">
        <div className="flex items-center gap-2.5">
          <LogoMark size={32} className="shrink-0 rounded-md ring-1 ring-white/25" />
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

      <div className="flex min-w-0 items-center justify-center p-6 bg-white">
        <div className={signingUp ? 'w-full max-w-md' : 'w-full max-w-sm'}>
          <div className="flex items-center justify-between mb-8">
            <div className="lg:hidden flex items-center gap-2.5">
              <LogoMark size={32} className="shrink-0 rounded-md" />
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

          {forgetting ? (
            <ForgotPassword email={email} onBack={() => setForgetting(false)} />
          ) : signingUp ? (
            <div>
              <h1 className="text-xl font-semibold text-gray-900 tracking-tight">{t('login.askAccess')}</h1>
              <p className="mt-1 text-sm text-gray-500">{t('login.askAccessHelp')}</p>
              <Link to="/pricing" className="mt-2 mb-6 inline-block text-sm text-brand-navy underline">
                {t('login.seePricing')}
              </Link>
              <SignupForm onBack={() => setSigningUp(false)} />
            </div>
          ) : (
            <form onSubmit={submit} noValidate>
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
                <div>
                  <Input
                    label={t('login.password')}
                    type="password"
                    revealable
                    autoComplete="current-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setForgetting(true)}
                    className="mt-2 text-sm text-brand-navy underline"
                  >
                    {t('login.forgot')}
                  </button>
                </div>
              </div>

              {error && (
                <p className="mt-4 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                  {error}
                </p>
              )}

              <Button type="submit" fullWidth isLoading={busy} className="mt-6">
                {t('login.submit')}
              </Button>

              <div className="mt-6 border-t border-gray-100 pt-4 text-sm text-gray-600">
                <p>
                  {t('login.noAccount')}{' '}
                  <button
                    type="button"
                    onClick={() => setSigningUp(true)}
                    className="font-medium text-brand-navy underline"
                  >
                    {t('login.askAccess')}
                  </button>
                </p>
                <Link to="/pricing" className="mt-2 inline-block text-brand-navy underline">
                  {t('login.seePricing')}
                </Link>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}

/**
 * « Mot de passe oublié »: an address in, a link out by e-mail.
 *
 * ⚠️ THE SAME ANSWER WHETHER THE ADDRESS HOLDS AN ACCOUNT OR NOT: the server words it, and
 * this screen shows it as it is. Telling « unknown address » apart would tell anybody which
 * addresses hold an account on a fund.
 */
function ForgotPassword({ email: typed, onBack }: { email: string; onBack: () => void }) {
  const { t } = useTranslation()
  const [email, setEmail] = useState(typed)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sent, setSent] = useState<string | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!email.trim()) {
      setError(t('login.forgotMissing'))
      return
    }
    setBusy(true)
    try {
      const { data } = await authApi.forgotPassword(email.trim())
      setSent(data.message)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <h1 className="text-xl font-semibold text-gray-900 tracking-tight">{t('login.forgotTitle')}</h1>
      <p className="mt-1 mb-6 text-sm text-gray-500">{t('login.forgotHelp')}</p>
      {sent ? (
        <Notice tone="info" title={t('login.forgotSentTitle')}>
          {sent}
        </Notice>
      ) : (
        <form onSubmit={submit} noValidate className="space-y-4">
          <Input
            label={t('login.email')}
            hint={t('login.forgotEmailHint')}
            type="email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          {error && (
            <p className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {error}
            </p>
          )}
          <Button type="submit" fullWidth isLoading={busy}>
            {t('login.forgotSubmit')}
          </Button>
        </form>
      )}
      <button type="button" onClick={onBack} className="mt-6 text-sm text-brand-navy underline">
        {t('login.backToSignIn')}
      </button>
    </div>
  )
}
